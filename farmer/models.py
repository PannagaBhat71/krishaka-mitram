from django.db import models
from django.conf import settings

# Create your models here.

class Farmer(models.Model):
    name = models.CharField(max_length = 100)
    crop_type = models.CharField(max_length = 100)
    crop_name = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete = models.CASCADE)
    price = models.DecimalField(max_digits = 10,decimal_places = 2)
    location = models.CharField(max_length = 100)
    farm_size = models.DecimalField(max_digits = 10,decimal_places = 2)
    quality = models.DecimalField(max_digits = 10,decimal_places = 2)
    quantity = models.DecimalField(max_digits = 10,decimal_places = 2)
    date_posted = models.DateField(auto_now_add = True)
    phone_number = models.IntegerField(max_length = 11)
    ration_card_number = models.IntegerField(max_length = 12)



    def __str__(self):
        return self.name



class Buyer(models.Model):
    name = models.CharField(max_length = 100)
    crop_type = models.ForeignKey(Farmer, on_delete = models.CASCADE)
    quantity = models.DecimalField(max_digits = 10,decimal_places = 2)
    budget = models.DecimalField(max_digits = 10,decimal_places = 2)


    def __str__(self):
        return self.name
    
