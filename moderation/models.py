from django.db import models
from django.conf import settings
from django.utils import timezone


class FilterRule(models.Model):
    RULE_TYPE_CHOICES = (
        ('phone', 'Phone Number'),
        ('email', 'Email Address'),
        ('upi', 'UPI ID'),
        ('bank', 'Bank Details'),
        ('url', 'URL / Social Media Link'),
        ('address', 'Physical Address'),
        ('keyword', 'Prohibited Keyword'),
        ('custom', 'Custom Regex'),
    )

    ACTION_CHOICES = (
        ('block', 'Block Message'),
        ('warn', 'Warn User & Allow'),
        ('log', 'Log Only'),
    )

    SEVERITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    )

    name = models.CharField(max_length=100, unique=True)
    pattern = models.TextField(help_text="Regex pattern for detection")
    rule_type = models.CharField(max_length=20, choices=RULE_TYPE_CHOICES)
    is_active = models.BooleanField(default=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    action = models.CharField(max_length=10, choices=ACTION_CHOICES, default='log')
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-severity', 'name']
        verbose_name = 'Filter Rule'
        verbose_name_plural = 'Filter Rules'

    def __str__(self):
        return f"{self.name} ({self.get_rule_type_display()})"


class ModerationIncident(models.Model):
    """
    Groups one or more ModerationViolation records originating from the same
    submission (blocked message or filtered message). This provides a stable
    identity for the submission lifecycle and prevents duplicate full-message
    copies across multiple violations.
    """
    STATUS_CHOICES = (
        ('NEW', 'New'),
        ('VIEWED', 'Viewed'),
        ('PENDING_ACTION', 'Pending Action'),
        ('RESOLVED', 'Resolved'),
    )

    # Core identification - always populated for blocked submissions
    conversation = models.ForeignKey(
        'chat.Conversation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderation_incidents'
    )
    submitting_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderation_incidents'
    )
    # For filtered messages that created a Message record
    message = models.ForeignKey(
        'chat.Message',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderation_incidents'
    )

    # The full blocked message content - stored ONLY here, not duplicated
    # across violations. Purged on first VIEWED transition.
    blocked_content = models.TextField(
        blank=True,
        help_text="Full blocked message content (temporary, purged on first view)"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='NEW',
        db_index=True
    )
    assigned_moderator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_incidents'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    viewed_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution = models.TextField(blank=True)
    action_taken = models.TextField(blank=True)

    # Sensitive content lifecycle - single source of truth for purge state
    sensitive_data_purged = models.BooleanField(default=False)
    purge_scheduled_at = models.DateTimeField(null=True, blank=True)
    purged_at = models.DateTimeField(null=True, blank=True)
    purged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purged_incidents'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Moderation Incident'
        verbose_name_plural = 'Moderation Incidents'

    def __str__(self):
        return f"Incident #{self.id} - {self.get_status_display()} - {self.conversation_id or 'N/A'}"

    def mark_viewed(self, moderator):
        """Mark as viewed AND permanently purge blocked content from active record."""
        if self.status == 'NEW':
            self.status = 'VIEWED'
            self.viewed_at = timezone.now()
            self.assigned_moderator = moderator
            # Purge blocked_content immediately when marked as viewed
            if self.blocked_content:
                self.blocked_content = ""
            self.save(update_fields=['status', 'viewed_at', 'assigned_moderator', 'blocked_content'])
            # Propagate to related violations (atomic cascade) - violations use detected_content
            self.violations.filter(status='NEW').update(
                status='VIEWED',
                viewed_at=timezone.now(),
                assigned_moderator=moderator
            )

    def mark_pending_action(self):
        if self.status == 'VIEWED':
            self.status = 'PENDING_ACTION'
            self.save(update_fields=['status'])
            self.violations.filter(status='VIEWED').update(status='PENDING_ACTION')

    def resolve(self, moderator, resolution, action_taken=''):
        self.status = 'RESOLVED'
        self.resolved_at = timezone.now()
        self.resolution = resolution
        self.action_taken = action_taken
        self.assigned_moderator = moderator
        # Schedule sensitive data purge based on configured retention
        from django.conf import settings as django_settings
        purge_days = getattr(django_settings, 'VIOLATION_AUTO_PURGE_DAYS', 30)
        self.purge_scheduled_at = timezone.now() + timezone.timedelta(days=purge_days)
        self.save(update_fields=[
            'status', 'resolved_at', 'resolution', 'action_taken',
            'assigned_moderator', 'purge_scheduled_at'
        ])
        # Propagate to related violations
        self.violations.exclude(status='RESOLVED').update(
            status='RESOLVED',
            resolved_at=timezone.now(),
            resolution=resolution,
            action_taken=action_taken,
            assigned_moderator=moderator,
            purge_scheduled_at=self.purge_scheduled_at
        )

    def purge_sensitive_data(self, purged_by):
        """Permanently delete sensitive content after review."""
        self.blocked_content = ""
        self.sensitive_data_purged = True
        self.purged_at = timezone.now()
        self.purged_by = purged_by
        self.save(update_fields=['blocked_content', 'sensitive_data_purged', 'purged_at', 'purged_by'])
        # Purge all related violations
        self.violations.filter(sensitive_data_purged=False).update(
            detected_content='[PURGED]',
            sensitive_data_purged=True,
            purged_at=timezone.now(),
            purged_by=purged_by
        )

    @property
    def detected_content_purged(self):
        """Check if detected content has been purged across all violations."""
        if not self.violations.exists():
            return self.sensitive_data_purged
        return self.violations.filter(sensitive_data_purged=True).count() == self.violations.count()


class ModerationViolation(models.Model):
    STATUS_CHOICES = (
        ('NEW', 'New'),
        ('VIEWED', 'Viewed'),
        ('PENDING_ACTION', 'Pending Action'),
        ('RESOLVED', 'Resolved'),
    )

    # Link to the incident this violation belongs to (required)
    incident = models.ForeignKey(
        ModerationIncident,
        on_delete=models.CASCADE,
        related_name='violations',
        null=True,
        blank=True
    )
    # The rule that triggered this violation
    rule = models.ForeignKey(
        FilterRule,
        on_delete=models.PROTECT,
        related_name='violations'
    )
    # The specific detected sensitive content for this violation
    detected_content = models.TextField(
        help_text="The sensitive content that was detected (for display in moderation)"
    )
    # Individual violation status (follows incident state but can be queried independently)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='NEW',
        db_index=True
    )
    severity = models.CharField(max_length=10, choices=FilterRule.SEVERITY_CHOICES)
    assigned_moderator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_violations'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    viewed_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution = models.TextField(blank=True)
    action_taken = models.TextField(blank=True)

    # Sensitive content lifecycle - mirrors incident state
    sensitive_data_purged = models.BooleanField(default=False)
    purge_scheduled_at = models.DateTimeField(null=True, blank=True)
    purged_at = models.DateTimeField(null=True, blank=True)
    purged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purged_violations'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Moderation Violation'
        verbose_name_plural = 'Moderation Violations'

    def __str__(self):
        return f"Violation #{self.id} ({self.incident_id}) - {self.get_status_display()} - {self.rule.name}"

    def mark_viewed(self, moderator):
        """Delegate to incident for atomic state transition."""
        self.incident.mark_viewed(moderator)
        self.refresh_from_db()

    def mark_pending_action(self):
        self.incident.mark_pending_action()
        self.refresh_from_db()

    def resolve(self, moderator, resolution, action_taken=''):
        self.incident.resolve(moderator, resolution, action_taken)
        self.refresh_from_db()

    def purge_sensitive_data(self, purged_by):
        """Delegate to incident for atomic purge."""
        self.incident.purge_sensitive_data(purged_by)
        self.refresh_from_db()


class UserRestriction(models.Model):
    RESTRICTION_TYPE_CHOICES = (
        ('temporary', 'Temporary Restriction'),
        ('permanent', 'Permanent Ban'),
        ('chat_only', 'Chat-Only Restriction'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='restrictions'
    )
    # Reference to incident instead of individual violation
    incident = models.ForeignKey(
        ModerationIncident,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='user_restrictions'
    )
    # Keep backward compatibility with violation field
    violation = models.ForeignKey(
        ModerationViolation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='user_restrictions'
    )
    restriction_type = models.CharField(max_length=20, choices=RESTRICTION_TYPE_CHOICES)
    reason = models.TextField()
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_restrictions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'User Restriction'
        verbose_name_plural = 'User Restrictions'

    def __str__(self):
        return f"{self.user.username} - {self.get_restriction_type_display()} ({'Active' if self.is_active else 'Expired'})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update user's restriction status
        user = self.user
        user.is_restricted = self.is_active and (self.ends_at is None or self.ends_at > timezone.now())
        if self.is_active:
            user.restriction_reason = self.reason
            user.restriction_until = self.ends_at
        else:
            user.restriction_reason = ''
            user.restriction_until = None
        user.save(update_fields=['is_restricted', 'restriction_reason', 'restriction_until'])

    def deactivate(self):
        self.is_active = False
        self.save(update_fields=['is_active'])
        self.save()  # This will update the user's restriction status