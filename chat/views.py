from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Max
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.db import transaction
from farmer.models import Farmer
from .models import Conversation, Message
from moderation.models import ModerationIncident, ModerationViolation, FilterRule


def chat_login_view(request):
    """Separate login page for chat access."""
    if request.user.is_authenticated:
        return redirect('chat:chat_list')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_currently_restricted():
                messages.error(request, 'Your account is restricted from accessing chat.')
            else:
                login(request, user)
                return redirect('chat:chat_list')
        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'chat/login.html')


def chat_logout_view(request):
    """Logout from chat."""
    logout(request)
    messages.success(request, 'You have been logged out from chat.')
    return redirect('chat:chat_login')


@login_required
def chat_list_view(request):
    """List all conversations for the current user."""
    if request.user.is_currently_restricted():
        messages.error(request, 'Your account is restricted from accessing chat.')
        return redirect('chat:chat_logout')

    # Get conversations where user is either farmer or buyer
    conversations = Conversation.objects.filter(
        Q(farmer=request.user) | Q(buyer=request.user),
        is_active=True
    ).select_related('farmer', 'buyer', 'farmer_listing').prefetch_related('messages')

    # Annotate with last message
    conversation_data = []
    for conv in conversations:
        last_message = conv.messages.order_by('-created_at').first()
        other_user = conv.buyer if conv.farmer == request.user else conv.farmer
        unread_count = conv.messages.exclude(sender=request.user).filter(
            created_at__gt=request.user.last_login or timezone.now()
        ).count() if request.user.last_login else 0

        conversation_data.append({
            'conversation': conv,
            'other_user': other_user,
            'last_message': last_message,
            'unread_count': unread_count,
            'listing': conv.farmer_listing
        })

    context = {
        'conversations': conversation_data,
    }
    return render(request, 'chat/chat_list.html', context)


@login_required
def start_chat_view(request, farmer_id):
    """Start a new conversation with a farmer about a specific listing."""
    if request.user.is_currently_restricted():
        messages.error(request, 'Your account is restricted from starting chats.')
        return redirect('chat:chat_list')

    if request.user.role != 'buyer':
        messages.error(request, 'Only buyers can initiate conversations.')
        return redirect('farmer-detail', pk=farmer_id)

    listing = get_object_or_404(Farmer, id=farmer_id)

    # Check if conversation already exists
    conversation = Conversation.objects.filter(
        farmer=listing.posted_by,
        buyer=request.user,
        farmer_listing=listing,
        is_active=True
    ).first()

    if not conversation:
        if not listing.posted_by:
            messages.error(request, 'This listing does not have an associated farmer account.')
            return redirect('farmer-detail', pk=farmer_id)

        conversation = Conversation.objects.create(
            farmer=listing.posted_by,
            buyer=request.user,
            farmer_listing=listing
        )
        messages.success(request, 'Conversation started!')

    return redirect('chat:chat_detail', conversation_id=conversation.id)


@login_required
def start_chat_with_buyer_view(request, inquiry_id):
    """Start or retrieve a conversation with a buyer who inquired about a listing.

    This view is for farmers to initiate chat from their listing's incoming inquiries.
    """
    from farmer.models import Buyer as Inquiry

    if request.user.is_currently_restricted():
        messages.error(request, 'Your account is restricted from starting chats.')
        return redirect('chat:chat_list')

    # Get the inquiry
    inquiry = get_object_or_404(Inquiry, id=inquiry_id)

    # Verify the current user is the farmer who owns this listing
    if not inquiry.Farmer:
        messages.error(request, 'This inquiry is not associated with a valid listing.')
        return redirect('farmer-list')

    listing = inquiry.Farmer

    # Authorization: Only the listing owner (farmer) can start chat with the inquiring buyer
    if request.user != listing.posted_by and not request.user.is_superuser:
        messages.error(request, 'You are not authorized to start a chat for this inquiry.')
        return redirect('farmer-detail', pk=listing.pk)

    # Verify the buyer user exists
    if not inquiry.Buyer:
        messages.error(request, 'This inquiry does not have an associated buyer account.')
        return redirect('farmer-detail', pk=listing.pk)

    # Check if conversation already exists (reuse existing conversation)
    conversation = Conversation.objects.filter(
        farmer=request.user,
        buyer=inquiry.Buyer,
        farmer_listing=listing,
        is_active=True
    ).first()

    if not conversation:
        # Create new conversation
        conversation = Conversation.objects.create(
            farmer=request.user,
            buyer=inquiry.Buyer,
            farmer_listing=listing
        )
        messages.success(request, f'Conversation started with {inquiry.Buyer.username}!')

    return redirect('chat:chat_detail', conversation_id=conversation.id)


@login_required
def chat_detail_view(request, conversation_id):
    """View a specific conversation with message history."""
    if request.user.is_currently_restricted():
        messages.error(request, 'Your account is restricted from accessing chat.')
        return redirect('chat:chat_logout')

    conversation = get_object_or_404(
        Conversation.objects.select_related('farmer', 'buyer', 'farmer_listing'),
        id=conversation_id
    )

    # Verify user is participant
    if conversation.farmer != request.user and conversation.buyer != request.user:
        messages.error(request, 'You are not authorized to view this conversation.')
        return redirect('chat:chat_list')

    # Get messages
    chat_messages = conversation.messages.filter(is_deleted=False).select_related('sender').order_by('created_at')

    other_user = conversation.buyer if conversation.farmer == request.user else conversation.farmer

    context = {
        'conversation': conversation,
        'chat_messages': chat_messages,
        'other_user': other_user,
        'user_role': request.user.role,
    }
    return render(request, 'chat/chat_detail.html', context)


@login_required
@require_http_methods(["POST"])
def send_message_view(request, conversation_id):
    """API endpoint to send a message (fallback for non-WebSocket)."""
    if request.user.is_currently_restricted():
        return JsonResponse({'error': 'Account restricted'}, status=403)

    conversation = get_object_or_404(Conversation, id=conversation_id, is_active=True)

    if conversation.farmer != request.user and conversation.buyer != request.user:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    content = request.POST.get('content', '').strip()
    if not content:
        return JsonResponse({'error': 'Empty message'}, status=400)

    # Import filter engine
    from moderation.filters import message_filter_engine
    filter_result = message_filter_engine.filter_message(content)

    # Handle blocked messages - no Message record, create ModerationIncident with violations
    

    # Create message (only for non-blocked messages)
    message = Message.objects.create(
        conversation=conversation,
        sender=request.user,
        content=filter_result.filtered_content,
        is_filtered=not filter_result.is_clean,
        filter_types=filter_result.filter_types
    )

    conversation.save(update_fields=['updated_at'])

    # Handle violations if any (for filtered but not blocked messages)
    if not filter_result.is_clean:
        with transaction.atomic():
            incident = ModerationIncident.objects.create(
                conversation=conversation,
                submitting_user=request.user,
                message=message,
                blocked_content='',  # No blocked content for filtered messages
                status='NEW'
            )
            db_rules = list(FilterRule.objects.filter(is_active=True, rule_type__in=filter_result.filter_types))
            rule_map = {r.rule_type: r for r in db_rules}

            for violation in filter_result.violations:
                rule = rule_map.get(violation.rule_type)
                if not rule:
                    rule, _ = FilterRule.objects.get_or_create(
                        name=f"Auto: {violation.rule_name}",
                        defaults={
                            'pattern': '',
                            'rule_type': violation.rule_type,
                            'severity': violation.severity,
                            'action': violation.action,
                            'description': f"Auto-created rule for {violation.rule_type} detection"
                        }
                    )
                ModerationViolation.objects.create(
                    incident=incident,
                    rule=rule,
                    detected_content=violation.detected_text,
                    severity=violation.severity
                )

    return JsonResponse({
        'id': message.id,
        'content': filter_result.filtered_content,
        'is_filtered': not filter_result.is_clean,
        'filter_types': filter_result.filter_types,
        'created_at': message.created_at.isoformat(),
    })


@login_required
def close_conversation_view(request, conversation_id):
    """Close a conversation."""
    conversation = get_object_or_404(Conversation, id=conversation_id)

    if conversation.farmer != request.user and conversation.buyer != request.user:
        messages.error(request, 'Unauthorized')
        return redirect('chat:chat_list')

    conversation.close(request.user)
    messages.success(request, 'Conversation closed.')
    return redirect('chat:chat_list')