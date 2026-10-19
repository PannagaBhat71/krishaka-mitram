from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.utils import timezone
from .models import Notification


@login_required
def notification_list_view(request):
    """List all notifications for the current user."""
    notifications = Notification.objects.filter(recipient=request.user).select_related('content_type')

    paginator = Paginator(notifications, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Count unread
    unread_count = notifications.filter(is_read=False).count()

    context = {
        'page_obj': page_obj,
        'notifications': page_obj,
        'unread_count': unread_count,
    }
    return render(request, 'notifications/list.html', context)


@login_required
@require_http_methods(["POST"])
def mark_notification_read_view(request, notification_id):
    """Mark a single notification as read."""
    notification = get_object_or_404(Notification, id=notification_id, recipient=request.user)
    notification.mark_as_read()

    if request.headers.get('HX-Request'):
        return JsonResponse({'success': True})

    return redirect('notifications:notification_list')


@login_required
@require_http_methods(["POST"])
def mark_all_read_view(request):
    """Mark all notifications as read."""
    Notification.objects.filter(recipient=request.user, is_read=False).update(
        is_read=True,
        read_at=timezone.now()
    )
    messages.success(request, 'All notifications marked as read.')
    return redirect('notifications:notification_list')


@login_required
def api_notification_count(request):
    """API endpoint for unread notification count."""
    count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'unread_count': count})


@login_required
def api_recent_notifications(request):
    """API endpoint for recent unread notifications."""
    notifications = Notification.objects.filter(
        recipient=request.user,
        is_read=False
    ).order_by('-created_at')[:10]

    data = [{
        'id': n.id,
        'type': n.notification_type,
        'title': n.title,
        'message': n.message[:100] + ('...' if len(n.message) > 100 else ''),
        'created_at': n.created_at.isoformat(),
    } for n in notifications]

    return JsonResponse({'notifications': data})


# Import timezone for mark_all_read_view
from django.utils import timezone