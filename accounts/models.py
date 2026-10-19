from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

# Create your models here.
class CustomUser(AbstractUser):

    ROLE_CHOICES = (
        ('farmer', 'Farmer'),
        ('buyer', 'Buyer'),
        ('moderator', 'Moderator'),
        ('owner', 'Owner'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='buyer')

    # Moderation-related fields
    is_restricted = models.BooleanField(default=False)
    restriction_reason = models.TextField(blank=True)
    restriction_until = models.DateTimeField(null=True, blank=True)
    violation_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.username

    @property
    def is_moderator(self):
        return self.role in ['moderator', 'owner']

    @property
    def is_owner(self):
        return self.role == 'owner'

    def is_currently_restricted(self):
        """Check if user is currently under restriction."""
        if not self.is_restricted:
            return False
        if self.restriction_until and self.restriction_until < timezone.now():
            # Restriction expired
            self.is_restricted = False
            self.restriction_until = None
            self.save(update_fields=['is_restricted', 'restriction_until'])
            return False
        return True
