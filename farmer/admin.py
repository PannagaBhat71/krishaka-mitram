from django.contrib import admin
from .models import Crop, Farmer, Buyer

# Register your models here.

@admin.register(Crop)
class CropAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']
    search_fields = ['name']


@admin.register(Farmer)
class FarmerAdmin(admin.ModelAdmin):
    list_display = ['name', 'crop_name', 'crop_type', 'price', 'quantity', 'location', 'posted_by', 'date_posted']
    search_fields = ['name', 'crop_name__name', 'crop_type__name', 'location']
    list_filter = ['crop_type', 'location', 'date_posted']


@admin.register(Buyer)
class BuyerAdmin(admin.ModelAdmin):
    list_display = ['name', 'crop_type', 'quantity', 'budget']
    search_fields = ['name', 'crop_type__name']
    list_filter = ['crop_type']

