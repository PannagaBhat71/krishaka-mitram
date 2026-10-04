from django.conf.locale import ro
from django.db import models
from django.contrib.auth.models import AbstractUser

# Create your models here.
class CustomUser(AbstractUser):

    ROLE_CHOICES = (
        ('farmer','Farmer'),
        ('buyer','Buyer'),
    )

    role = models.CharField(max_length=20, choices = ROLE_CHOICES, default = 'buyer')


    def __str__(self):
        return self.username
