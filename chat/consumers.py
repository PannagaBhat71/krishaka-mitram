import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from moderation.filters import message_filter_engine, FilterResult
from moderation.models import ModerationViolation, FilterRule, ModerationIncident
from notifications.models import Notification
from audit.models import AuditLog
from .models import Conversation, Message

User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time chat between farmers and buyers.
    Handles authentication, message filtering, broadcasting, and violation recording.
    """

    async def connect(self):
        self.user = self.scope.get('user')

        # Require authenticated user
        if not self.user or self.user.is_anonymous:
            await self.close(code=4001)  # Unauthorized
            return

        # Check if user is restricted
        if await self._is_user_restricted():
            await self.close(code=4003)  # Restricted
            return

        # Get conversation ID from URL
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f'chat_{self.conversation_id}'

        # Verify user is part of this conversation
        if not await self._is_participant():
            await self.close(code=4004)  # Forbidden
            return

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to chat'
        }))

        # Log connection
        await self._log_audit('CONVERSATION_STARTED', object_id=self.conversation_id)

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type', 'message')

            if message_type == 'message':
                await self.handle_message(data)
            elif message_type == 'typing':
                await self.handle_typing(data)
            elif message_type == 'read_receipt':
                await self.handle_read_receipt(data)
            else:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': f'Unknown message type: {message_type}'
                }))
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))

    
    async def handle_message(self, data):
        """Filter, save, log, and broadcast a message exactly once."""
        content = data.get('content', '').strip()
        if not content:
            return

        if not await self._is_conversation_active():
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Conversation is closed'
            }))
            return

        if await self._is_user_restricted():
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Your account is restricted from chatting'
            }))
            return

        # Filter once. Content-based detections do not block sending.
        filter_result = await self._filter_message(content)

        # Save exactly one message, using the filtered content.
        message = await self._create_message(filter_result)

        # Record moderation incidents for flagged messages.
        if not filter_result.is_clean:
            await self._handle_violations(message, filter_result)

        # Broadcast exactly once to the conversation group.
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message_id': message.id,
                'sender_id': self.user.id,
                'sender_username': self.user.username,
                'content': filter_result.filtered_content,
                'is_filtered': not filter_result.is_clean,
                'filter_types': filter_result.filter_types,
                'created_at': message.created_at.isoformat(),
            }
        )

        # Notify the other participant exactly once.
        await self._notify_other_participant(
            message
            )


    async def handle_typing(self, data):
        """Broadcast typing indicator."""
        is_typing = data.get('is_typing', False)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_typing',
                'user_id': self.user.id,
                'username': self.user.username,
                'is_typing': is_typing
            }
        )

    async def handle_read_receipt(self, data):
        """Handle read receipts."""
        message_id = data.get('message_id')
        if message_id:
            await self._mark_message_read(message_id)

    # Channel layer message handlers
    async def chat_message(self, event):
        """Send message to WebSocket."""
        await self.send(text_data=json.dumps(event))

    async def user_typing(self, event):
        """Send typing indicator to WebSocket."""
        await self.send(text_data=json.dumps(event))

    async def violation_notification(self, event):
        """Send violation notification to moderators."""
        await self.send(text_data=json.dumps(event))

    # Database operations
    @database_sync_to_async
    def _is_participant(self):
        try:
            conversation = Conversation.objects.get(id=self.conversation_id, is_active=True)
            return conversation.farmer == self.user or conversation.buyer == self.user
        except Conversation.DoesNotExist:
            return False

    @database_sync_to_async
    def _is_conversation_active(self):
        try:
            conversation = Conversation.objects.get(id=self.conversation_id)
            return conversation.is_active
        except Conversation.DoesNotExist:
            return False

    @database_sync_to_async
    def _is_user_restricted(self):
        return self.user.is_currently_restricted()

    @database_sync_to_async
    def _filter_message(self, content: str) -> FilterResult:
        return message_filter_engine.filter_message(content)

    @database_sync_to_async
    def _create_message(self, filter_result: FilterResult) -> Message:
        conversation = Conversation.objects.get(id=self.conversation_id)
        message = Message.objects.create(
            conversation=conversation,
            sender=self.user,
            content=filter_result.filtered_content,
            is_filtered=not filter_result.is_clean,
            filter_types=filter_result.filter_types
        )
        # Update conversation updated_at
        conversation.save(update_fields=['updated_at'])
        return message

    @database_sync_to_async
    def _handle_blocked_message(self, filter_result: FilterResult):
        """Create incident and violation records for blocked messages without creating a Message."""
        with transaction.atomic():
            conversation = Conversation.objects.get(id=self.conversation_id)
            incident = ModerationIncident.objects.create(
                conversation=conversation,
                submitting_user=self.user,
                message=None,
                blocked_content=filter_result.original_content,
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

            # NOTIFY MODERATORS: The post_save signal on ModerationIncident handles this
            # (see moderation/signals.py notify_moderators_on_incident_creation)
            # Do NOT call _notify_moderators_sync() here to avoid duplicates.

    @database_sync_to_async
    def _handle_violations(self, message: Message, filter_result: FilterResult):
        """Create incident and violation records for filtered content."""
        with transaction.atomic():
            incident = ModerationIncident.objects.create(
                conversation=message.conversation,
                submitting_user=self.user,
                message=message,
                blocked_content='',
                status='NEW'
            )
            db_rules = list(FilterRule.objects.filter(is_active=True, rule_type__in=filter_result.filter_types))
            rule_map = {r.rule_type: r for r in db_rules}

            for violation in filter_result.violations:
                rule = rule_map.get(violation.rule_type)
                if not rule:
                    # Create a default rule for built-in detections
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

            # NOTIFY MODERATORS: The post_save signal on ModerationIncident handles this
            # (see moderation/signals.py notify_moderators_on_incident_creation)
            # Do NOT call _notify_moderators_sync() here to avoid duplicates.

    @database_sync_to_async
    def _notify_other_participant(self, message: Message):
        """Create notification for the other participant."""
        conversation = message.conversation
        other_user = conversation.farmer if message.sender == conversation.buyer else conversation.buyer

        Notification.create_notification(
            recipient=other_user,
            notification_type='chat_message',
            title=f"New message from {message.sender.username}",
            message=message.content[:100] + ('...' if len(message.content) > 100 else ''),
            content_object=message
        )

    @database_sync_to_async
    def _mark_message_read(self, message_id: int):
        # Could implement read receipt logic here
        pass

    @database_sync_to_async
    def _log_audit(self, action: str, object_id: str = '', details: dict = None):
        AuditLog.log(
            action=action,
            actor=self.user,
            object_type='Conversation',
            object_id=object_id,
            details=details or {}
        )

    @database_sync_to_async
    def _notify_moderators(self, incident: ModerationIncident):
        """Send real-time notification to moderators group about new incident."""
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        channel_layer = get_channel_layer()
        if channel_layer:
            # Send to moderators group
            async_to_sync(channel_layer.group_send)(
                'moderators',
                {
                    'type': 'moderation_incident',
                    'incident_id': incident.id,
                    'conversation_id': incident.conversation_id,
                    'submitting_user': incident.submitting_user.username if incident.submitting_user else None,
                    'status': incident.status,
                    'violation_count': incident.violations.count(),
                    'severity': incident.violations.first().severity if incident.violations.exists() else 'unknown',
                    'created_at': incident.created_at.isoformat(),
                    'has_blocked_content': bool(incident.blocked_content),
                }
            )

        # Also create database notifications for each moderator
        moderators = User.objects.filter(role__in=['moderator', 'owner'], is_active=True)
        for moderator in moderators:
            Notification.create_notification(
                recipient=moderator,
                notification_type='violation_new',
                title='New Moderation Incident',
                message=f'Incident #{incident.id} in conversation #{incident.conversation_id} with {incident.violations.count()} violation(s)',
                content_object=incident
            )

    def _notify_moderators_sync(self, incident: ModerationIncident):
        """Synchronous version for use in @database_sync_to_async methods."""
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        channel_layer = get_channel_layer()
        if channel_layer:
            # Send to moderators group
            async_to_sync(channel_layer.group_send)(
                'moderators',
                {
                    'type': 'moderation_incident',
                    'incident_id': incident.id,
                    'conversation_id': incident.conversation_id,
                    'submitting_user': incident.submitting_user.username if incident.submitting_user else None,
                    'status': incident.status,
                    'violation_count': incident.violations.count(),
                    'severity': incident.violations.first().severity if incident.violations.exists() else 'unknown',
                    'created_at': incident.created_at.isoformat(),
                    'has_blocked_content': bool(incident.blocked_content),
                }
            )

        # Also create database notifications for each moderator
        moderators = User.objects.filter(role__in=['moderator', 'owner'], is_active=True)
        for moderator in moderators:
            Notification.create_notification(
                recipient=moderator,
                notification_type='violation_new',
                title='New Moderation Incident',
                message=f'Incident #{incident.id} in conversation #{incident.conversation_id} with {incident.violations.count()} violation(s)',
                content_object=incident
            )


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time notifications.
    """

    async def connect(self):
        self.user = self.scope.get('user')

        if not self.user or self.user.is_anonymous:
            await self.close(code=4001)
            return

        self.user_group_name = f'notifications_{self.user.id}'

        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if data.get('type') == 'mark_read':
                notification_id = data.get('notification_id')
                if notification_id:
                    await self._mark_notification_read(notification_id)
        except json.JSONDecodeError:
            pass

    async def notification_message(self, event):
        """Send notification to WebSocket."""
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def _mark_notification_read(self, notification_id: int):
        from notifications.models import Notification
        try:
            notification = Notification.objects.get(id=notification_id, recipient=self.user)
            notification.mark_as_read()
        except Notification.DoesNotExist:
            pass


class ModeratorConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time moderator notifications.
    Moderators join the 'moderators' group to receive incident alerts.
    """

    async def connect(self):
        self.user = self.scope.get('user')

        if not self.user or self.user.is_anonymous or not self.user.is_moderator:
            await self.close(code=4003)  # Forbidden - not a moderator
            return

        self.moderator_group_name = 'moderators'

        await self.channel_layer.group_add(
            self.moderator_group_name,
            self.channel_name
        )

        await self.accept()

        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to moderator notifications'
        }))

    async def disconnect(self, close_code):
        if hasattr(self, 'moderator_group_name'):
            await self.channel_layer.group_discard(
                self.moderator_group_name,
                self.channel_name
            )

    async def moderation_incident(self, event):
        """Send incident notification to WebSocket."""
        await self.send(text_data=json.dumps(event))