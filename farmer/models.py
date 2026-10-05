from django.db import models
from django.conf import settings

# Create your models here.

class Crop(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Farmer(models.Model):
    name = models.CharField(max_length = 100)
    crop_type = models.ForeignKey(Crop, on_delete = models.CASCADE, related_name = 'farmer_crop_types')
    crop_name = models.ForeignKey(Crop, on_delete = models.CASCADE, related_name = 'farmer_crops')
    price = models.DecimalField(max_digits = 10,decimal_places = 2)
    location = models.CharField(max_length = 100)
    farm_size = models.DecimalField(max_digits = 10,decimal_places = 2)
    quality = models.DecimalField(max_digits = 10,decimal_places = 2)
    quantity = models.DecimalField(max_digits = 10,decimal_places = 2)
    date_posted = models.DateField(auto_now_add = True)
    phone_number = models.CharField(max_length = 15)
    ration_card_number = models.CharField(max_length = 20)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete = models.CASCADE,
        null = True,
        blank = True,
        related_name = 'farmer_listings'
    )

    def __str__(self):
        return f"{self.name} - {self.crop_name}"



class Buyer(models.Model):
    Farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, null=True, blank=True, related_name='inquiries')
    Buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='buyer_interests')
    name = models.CharField(max_length=100, blank=True, default='')
    crop_type = models.ForeignKey(Crop, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    budget = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    message = models.TextField(blank=True, default='')
    date_applied = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        if self.Farmer and self.Buyer:
            return f"Interest by {self.Buyer} for {self.Farmer.name}"
        return self.name or f"Buyer #{self.id}"
    
