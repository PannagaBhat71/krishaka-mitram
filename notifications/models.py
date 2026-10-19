from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('violation_new', 'New Violation Detected'),
        ('violation_assigned', 'Violation Assigned to You'),
        ('violation_resolved', 'Violation Resolved'),
        ('user_restricted', 'User Restricted'),
        ('user_unrestricted', 'User Restriction Lifted'),
        ('chat_message', 'New Chat Message'),
        ('chat_started', 'New Conversation Started'),
        ('rule_triggered', 'Filter Rule Triggered'),
        ('system', 'System Notification'),
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES, db_index=True)
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    # Generic foreign key for related object
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    object_id = models.CharField(max_length=100, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at']),
        ]

    def __str__(self):
        return f"{self.recipient.username}: {self.title} ({'Read' if self.is_read else 'Unread'})"

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    @classmethod
    def create_notification(cls, recipient, notification_type, title, message, content_object=None):
        """Create a notification with optional related object."""
        from django.utils import timezone
        notification = cls.objects.create(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
        )
        if content_object:
            notification.content_type = ContentType.objects.get_for_model(content_object)
            notification.object_id = str(content_object.pk)
            notification.save(update_fields=['content_type', 'object_id'])
        return notification


# Import timezone for the classmethod
from django.utils import timezone