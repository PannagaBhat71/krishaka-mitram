from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from asgiref.sync import async_to_sync
from .models import ModerationIncident
from notifications.models import Notification
from django.contrib.auth import get_user_model

User = get_user_model()


def send_moderator_notifications(incident):
    """
    Send real-time notification to moderators group and create database notifications
    for a given ModerationIncident.
    """
    # Send to moderators group via Channels - call get_channel_layer() dynamically
    # so it can be properly patched in tests
    from channels.layers import get_channel_layer
    channel_layer = get_channel_layer()
    if channel_layer:
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

    # Create database notifications for each moderator
    # is_moderator is a property, filter by role instead
    moderators = User.objects.filter(role__in=['moderator', 'owner'], is_active=True)
    for moderator in moderators:
        Notification.create_notification(
            recipient=moderator,
            notification_type='violation_new',
            title='New Moderation Incident',
            message=f'Incident #{incident.id} in conversation #{incident.conversation_id} with {incident.violations.count()} violation(s)',
            content_object=incident
        )


@receiver(post_save, sender=ModerationIncident)
def notify_moderators_on_incident_creation(sender, instance, created, **kwargs):
    """
    Send real-time notification to moderators group and create database notifications
    when a new ModerationIncident is created.
    Uses transaction.on_commit to ensure related objects are visible.
    """
    if not created:
        return

    # Use transaction.on_commit to ensure that when this function runs,
    # all related objects (like violations) created in the same transaction
    # are visible to the database queries.
    def send_notifications():
        send_moderator_notifications(instance)

    transaction.on_commit(send_notifications)