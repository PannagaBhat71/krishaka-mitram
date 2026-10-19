from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Count, Case, When, IntegerField
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from .models import FilterRule, ModerationViolation, UserRestriction, ModerationIncident
from chat.models import Conversation, Message
from notifications.models import Notification
from audit.models import AuditLog


def is_moderator(user):
    return user.is_authenticated and user.is_moderator


def is_owner(user):
    return user.is_authenticated and user.is_owner


def moderation_login_view(request):
    """Separate login page for moderation dashboard."""
    if request.user.is_authenticated and request.user.is_moderator:
        return redirect('moderation_dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None and user.is_moderator:
            login(request, user)
            AuditLog.log('LOGIN', actor=user, object_type='ModerationSession',
                        object_id=str(user.id), details={'type': 'moderation_dashboard'})
            return redirect('moderation_dashboard')
        else:
            messages.error(request, 'Invalid credentials or insufficient permissions.')
            AuditLog.log('FAILED_LOGIN', actor=user, object_type='ModerationSession',
                        object_id=username, details={'type': 'moderation_dashboard', 'reason': 'insufficient_perms'})

    return render(request, 'moderation/login.html')


def moderation_logout_view(request):
    """Logout from moderation dashboard."""
    user = request.user
    if user.is_authenticated:
        AuditLog.log('LOGOUT', actor=user, object_type='ModerationSession',
                    object_id=str(user.id), details={'type': 'moderation_dashboard'})
    logout(request)
    messages.success(request, 'Logged out from moderation dashboard.')
    return redirect('moderation_login')


@login_required
@user_passes_test(is_moderator)
def moderation_dashboard_view(request):
    """Main moderation dashboard with violation list and filters."""
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    severity_filter = request.GET.get('severity', '')
    rule_type_filter = request.GET.get('rule_type', '')
    assigned_filter = request.GET.get('assigned', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    search = request.GET.get('search', '')

    # Query incidents with related data
    incidents = ModerationIncident.objects.select_related(
        'conversation', 'conversation__farmer', 'conversation__buyer',
        'conversation__farmer_listing', 'submitting_user', 'assigned_moderator'
    ).prefetch_related('violations__rule').all()

    # Apply filters
    if status_filter:
        incidents = incidents.filter(status=status_filter)

    if severity_filter:
        incidents = incidents.filter(violations__severity=severity_filter).distinct()

    if rule_type_filter:
        incidents = incidents.filter(violations__rule__rule_type=rule_type_filter).distinct()

    if assigned_filter == 'me':
        incidents = incidents.filter(assigned_moderator=request.user)
    elif assigned_filter == 'unassigned':
        incidents = incidents.filter(assigned_moderator__isnull=True)

    if date_from:
        incidents = incidents.filter(created_at__date__gte=date_from)
    if date_to:
        incidents = incidents.filter(created_at__date__lte=date_to)

    if search:
        incidents = incidents.filter(
            Q(submitting_user__username__icontains=search) |
            Q(conversation__id__icontains=search) |
            Q(violations__rule__name__icontains=search) |
            Q(violations__detected_content__icontains=search) |
            Q(blocked_content__icontains=search)
        ).distinct()

    # Pagination
    paginator = Paginator(incidents, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Stats for dashboard cards - based on incidents
    stats = {
        'new': ModerationIncident.objects.filter(status='NEW').count(),
        'viewed': ModerationIncident.objects.filter(status='VIEWED').count(),
        'pending': ModerationIncident.objects.filter(status='PENDING_ACTION').count(),
        'resolved': ModerationIncident.objects.filter(status='RESOLVED').count(),
        'my_assigned': ModerationIncident.objects.filter(assigned_moderator=request.user).exclude(status='RESOLVED').count(),
        'total_active': ModerationIncident.objects.exclude(status='RESOLVED').count(),
    }

    context = {
        'page_obj': page_obj,
        'stats': stats,
        'status_choices': ModerationIncident.STATUS_CHOICES,
        'severity_choices': FilterRule.SEVERITY_CHOICES,
        'rule_type_choices': FilterRule.RULE_TYPE_CHOICES,
        'current_filters': {
            'status': status_filter,
            'severity': severity_filter,
            'rule_type': rule_type_filter,
            'assigned': assigned_filter,
            'date_from': date_from,
            'date_to': date_to,
            'search': search,
        }
    }
    return render(request, 'moderation/dashboard.html', context)


@login_required
@user_passes_test(is_moderator)
def incident_detail_view(request, incident_id):
    """Detailed view of a single moderation incident with all its violations."""
    incident = get_object_or_404(
        ModerationIncident.objects.select_related(
            'conversation', 'conversation__farmer', 'conversation__buyer',
            'conversation__farmer_listing', 'submitting_user', 'assigned_moderator'
        ).prefetch_related('violations__rule'),
        id=incident_id
    )

    # Get conversation context (if message or conversation exists)
    conversation = incident.conversation
    message = incident.message
    other_messages = None

    if conversation and message:
        other_messages = conversation.messages.filter(
            created_at__range=(
                message.created_at - timezone.timedelta(minutes=30),
                message.created_at + timezone.timedelta(minutes=30)
            )
        ).exclude(id=message.id).order_by('created_at')
    elif conversation and not message:
        # Blocked message - get recent messages in conversation
        other_messages = conversation.messages.filter(is_deleted=False).order_by('-created_at')[:20]

    context = {
        'incident': incident,
        'conversation': conversation,
        'message': message,
        'other_messages': other_messages,
        'status_choices': ModerationIncident.STATUS_CHOICES,
    }
    return render(request, 'moderation/incident_detail.html', context)


@login_required
@user_passes_test(is_moderator)
@require_http_methods(["POST"])
def incident_action_view(request, incident_id):
    """Handle moderation actions: resolve, warn, restrict, purge."""
    incident = get_object_or_404(ModerationIncident, id=incident_id)
    action = request.POST.get('action')
    resolution = request.POST.get('resolution', '')

    with transaction.atomic():
        if action == 'mark_viewed':
            incident.mark_viewed(request.user)
            AuditLog.log('VIEW_VIOLATION', actor=request.user,
                        object_type='ModerationIncident', object_id=str(incident.id))
            messages.success(request, 'Incident marked as viewed.')

        elif action == 'mark_pending':
            incident.mark_pending_action()
            messages.success(request, 'Incident marked as pending action.')

        elif action == 'resolve':
            incident.resolve(request.user, resolution)
            # Notify the user who sent the message
            if incident.submitting_user:
                Notification.create_notification(
                    recipient=incident.submitting_user,
                    notification_type='violation_resolved',
                    title='Moderation Update',
                    message=f'Your message in conversation #{incident.conversation_id} was reviewed. {resolution[:100]}',
                    content_object=incident
                )
            AuditLog.log('RESOLVE_VIOLATION', actor=request.user,
                        object_type='ModerationIncident', object_id=str(incident.id),
                        details={'resolution': resolution[:200]})
            messages.success(request, 'Incident resolved.')

        elif action == 'warn_user':
            if incident.submitting_user:
                user = incident.submitting_user
                user.violation_count += 1
                user.save(update_fields=['violation_count'])
                Notification.create_notification(
                    recipient=user,
                    notification_type='violation_new',
                    title='Warning: Policy Violation',
                    message=f'Your message was flagged for: {incident.violations.first().rule.name if incident.violations.exists() else "policy violation"}. Please review our communication policy.',
                    content_object=incident
                )
                AuditLog.log('WARN_USER', actor=request.user,
                            object_type='CustomUser', object_id=str(user.id),
                            details={'incident_id': incident.id, 'rule': incident.violations.first().rule.name if incident.violations.exists() else 'unknown'})
                messages.success(request, f'Warning issued to {user.username}. Total warnings: {user.violation_count}')

        elif action == 'restrict_user':
            if incident.submitting_user:
                user = incident.submitting_user
                try:
                    duration_days = int(request.POST.get('duration_days', 7))
                    if duration_days < 1 or duration_days > 365:
                        raise ValueError("Duration must be 1-365 days")
                except ValueError:
                    messages.error(request, 'Invalid duration. Must be 1-365 days.')
                    return redirect('moderation_incident_detail', incident_id=incident.id)

                restriction = UserRestriction.objects.create(
                    user=user,
                    incident=incident,
                    restriction_type='temporary',
                    reason=f"Moderation action: {resolution or incident.violations.first().rule.name if incident.violations.exists() else 'policy violation'}",
                    ends_at=timezone.now() + timezone.timedelta(days=duration_days),
                    created_by=request.user
                )
                Notification.create_notification(
                    recipient=user,
                    notification_type='user_restricted',
                    title='Account Temporarily Restricted',
                    message=f'Your chat access has been restricted for {duration_days} days due to policy violations.',
                    content_object=restriction
                )
                AuditLog.log('RESTRICT_USER', actor=request.user,
                            object_type='CustomUser', object_id=str(user.id),
                            details={'restriction_id': restriction.id, 'duration_days': duration_days})
                messages.success(request, f'{user.username} restricted for {duration_days} days.')

        elif action == 'permanent_ban':
            if incident.submitting_user:
                user = incident.submitting_user
                restriction = UserRestriction.objects.create(
                    user=user,
                    incident=incident,
                    restriction_type='permanent',
                    reason=f"Permanent ban: {resolution or 'Repeated severe violations'}",
                    ends_at=None,
                    created_by=request.user
                )
                AuditLog.log('RESTRICT_USER', actor=request.user,
                            object_type='CustomUser', object_id=str(user.id),
                            details={'restriction_id': restriction.id, 'type': 'permanent'})
                messages.success(request, f'{user.username} permanently banned.')

        elif action == 'purge_sensitive':
            if not incident.sensitive_data_purged:
                incident.purge_sensitive_data(request.user)
                AuditLog.log('PURGE_SENSITIVE_DATA', actor=request.user,
                            object_type='ModerationIncident', object_id=str(incident.id))
                messages.success(request, 'Sensitive content purged.')

    return redirect('moderation_incident_detail', incident_id=incident.id)


@login_required
@user_passes_test(is_owner)
def filter_rules_view(request):
    """Manage filter rules (owner only)."""
    rules = FilterRule.objects.all().order_by('-severity', 'name')

    if request.method == 'POST':
        form_action = request.POST.get('form_action', request.POST.get('action'))

        if form_action == 'create':
            rule = FilterRule.objects.create(
                name=request.POST.get('name'),
                pattern=request.POST.get('pattern', ''),
                rule_type=request.POST.get('rule_type'),
                severity=request.POST.get('severity', 'medium'),
                action=request.POST.get('enforcement_action', request.POST.get('action', 'log')),
                description=request.POST.get('description', ''),
            )
            AuditLog.log('CREATE_RULE', actor=request.user,
                        object_type='FilterRule', object_id=str(rule.id),
                        details={'name': rule.name, 'type': rule.rule_type})
            messages.success(request, f'Rule "{rule.name}" created.')

        elif form_action == 'update':
            rule_id = request.POST.get('rule_id')
            rule = get_object_or_404(FilterRule, id=rule_id)
            rule.name = request.POST.get('name')
            rule.pattern = request.POST.get('pattern', '')
            rule.rule_type = request.POST.get('rule_type')
            rule.severity = request.POST.get('severity', 'medium')
            rule.action = request.POST.get('enforcement_action', request.POST.get('action', 'log'))
            rule.description = request.POST.get('description', '')
            rule.save()
            AuditLog.log('UPDATE_RULE', actor=request.user,
                        object_type='FilterRule', object_id=str(rule.id))
            messages.success(request, f'Rule "{rule.name}" updated.')

        elif form_action == 'toggle':
            rule_id = request.POST.get('rule_id')
            rule = get_object_or_404(FilterRule, id=rule_id)
            rule.is_active = not rule.is_active
            rule.save(update_fields=['is_active'])
            AuditLog.log('TOGGLE_RULE', actor=request.user,
                        object_type='FilterRule', object_id=str(rule.id),
                        details={'is_active': rule.is_active})
            messages.success(request, f'Rule "{rule.name}" {"enabled" if rule.is_active else "disabled"}.')

        elif form_action == 'delete':
            rule_id = request.POST.get('rule_id')
            rule = get_object_or_404(FilterRule, id=rule_id)
            rule_name = rule.name
            rule.delete()
            AuditLog.log('DELETE_RULE', actor=request.user,
                        object_type='FilterRule', object_id=str(rule_id),
                        details={'name': rule_name})
            messages.success(request, f'Rule "{rule_name}" deleted.')

        return redirect('moderation:filter_rules')

    context = {
        'rules': rules,
        'rule_type_choices': FilterRule.RULE_TYPE_CHOICES,
        'severity_choices': FilterRule.SEVERITY_CHOICES,
        'action_choices': FilterRule.ACTION_CHOICES,
    }
    return render(request, 'moderation/filter_rules.html', context)


@login_required
@user_passes_test(is_owner)
def user_restrictions_view(request):
    """View and manage user restrictions (owner only)."""
    restrictions = UserRestriction.objects.select_related(
        'user', 'incident', 'violation', 'created_by'
    ).order_by('-created_at')

    paginator = Paginator(restrictions, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'restriction_type_choices': UserRestriction.RESTRICTION_TYPE_CHOICES,
    }
    return render(request, 'moderation/user_restrictions.html', context)


@login_required
@user_passes_test(is_owner)
@require_http_methods(["POST"])
def lift_restriction_view(request, restriction_id):
    """Lift a user restriction (owner only)."""
    restriction = get_object_or_404(UserRestriction, id=restriction_id)
    user = restriction.user
    restriction.deactivate()
    Notification.create_notification(
        recipient=user,
        notification_type='user_unrestricted',
        title='Restriction Lifted',
        message='Your chat access has been restored. Please adhere to our communication policy.',
        content_object=restriction
    )
    AuditLog.log('UNRESTRICT_USER', actor=request.user,
                object_type='CustomUser', object_id=str(user.id),
                details={'restriction_id': restriction.id})
    messages.success(request, f'Restriction on {user.username} lifted.')
    return redirect('user_restrictions')


@login_required
@user_passes_test(is_moderator)
def api_unread_count(request):
    """API endpoint for real-time violation count."""
    counts = {
        'new': ModerationIncident.objects.filter(status='NEW').count(),
        'total_pending': ModerationIncident.objects.exclude(status='RESOLVED').count(),
        'my_assigned': ModerationIncident.objects.filter(assigned_moderator=request.user).exclude(status='RESOLVED').count(),
    }
    return JsonResponse(counts)


@login_required
@user_passes_test(is_moderator)
def api_notification_count(request):
    """API endpoint for notification count."""
    count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'unread_count': count})