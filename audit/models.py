from django.db import models
from django.conf import settings


class AuditLog(models.Model):
    ACTION_CHOICES = (
        ('LOGIN', 'User Login'),
        ('LOGOUT', 'User Logout'),
        ('FAILED_LOGIN', 'Failed Login Attempt'),
        ('VIEW_VIOLATION', 'Viewed Violation Record'),
        ('RESOLVE_VIOLATION', 'Resolved Violation Record'),
        ('WARN_USER', 'Issued Warning to User'),
        ('RESTRICT_USER', 'Applied User Restriction'),
        ('UNRESTRICT_USER', 'Lifted User Restriction'),
        ('CREATE_RULE', 'Created Filter Rule'),
        ('UPDATE_RULE', 'Updated Filter Rule'),
        ('DELETE_RULE', 'Deleted Filter Rule'),
        ('TOGGLE_RULE', 'Toggled Filter Rule'),
        ('PURGE_SENSITIVE_DATA', 'Purged Sensitive Violation Data'),
        ('MESSAGE_BLOCKED', 'Message Blocked by Filter'),
        ('MESSAGE_FLAGGED', 'Message Flagged by Filter'),
        ('CONVERSATION_STARTED', 'Conversation Started'),
        ('CONVERSATION_CLOSED', 'Conversation Closed'),
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_actions'
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, db_index=True)
    object_type = models.CharField(max_length=100, blank=True, db_index=True)
    object_id = models.CharField(max_length=100, blank=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'

    def __str__(self):
        actor_name = self.actor.username if self.actor else 'System'
        return f"[{self.created_at:%Y-%m-%d %H:%M:%S}] {actor_name} -> {self.get_action_display() or self.action}"

    @classmethod
    def log(cls, action, actor=None, object_type='', object_id='', details=None, ip_address=None, user_agent=''):
        """Convenience method to create an audit log entry."""
        if details is None:
            details = {}
        return cls.objects.create(
            action=action,
            actor=actor,
            object_type=object_type,
            object_id=str(object_id),
            details=details,
            ip_address=ip_address,
            user_agent=user_agent
        )
