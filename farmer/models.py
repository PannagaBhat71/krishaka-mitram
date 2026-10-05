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

    @property
    def crop_image(self):
        name = (self.crop_name.name if self.crop_name else '').lower()
        images = {
            'paddy': 'https://images.unsplash.com/photo-1586201375761-83865001e31c?auto=format&fit=crop&w=600&q=80',
            'rice': 'https://images.unsplash.com/photo-1586201375761-83865001e31c?auto=format&fit=crop&w=600&q=80',
            'arecanut': 'https://images.unsplash.com/photo-1596704017254-9b121068fb31?auto=format&fit=crop&w=600&q=80',
            'coconut': 'https://images.unsplash.com/photo-1544376798-89aa6b82c6cd?auto=format&fit=crop&w=600&q=80',
            'cashew': 'https://images.unsplash.com/photo-1509358271058-acd22cc93898?auto=format&fit=crop&w=600&q=80',
            'jowar': 'https://images.unsplash.com/photo-1574323347407-f5e1ad6d020b?auto=format&fit=crop&w=600&q=80',
            'sugarcane': 'https://images.unsplash.com/photo-1558435186-d31d126391fa?auto=format&fit=crop&w=600&q=80',
            'maize': 'https://images.unsplash.com/photo-1551754655-cd27e38d2076?auto=format&fit=crop&w=600&q=80',
            'cotton': 'https://images.unsplash.com/photo-1606041008023-472dfb5e530f?auto=format&fit=crop&w=600&q=80',
            'toor': 'https://images.unsplash.com/photo-1515543237350-b3eea1ec8082?auto=format&fit=crop&w=600&q=80',
            'ragi': 'https://images.unsplash.com/photo-1586771107445-d3ca888129ff?auto=format&fit=crop&w=600&q=80',
        }
        for key, url in images.items():
            if key in name:
                return url
        return 'https://images.unsplash.com/photo-1500937386664-56d1dfef3854?auto=format&fit=crop&w=600&q=80'



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
    
