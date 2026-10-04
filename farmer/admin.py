from django.contrib import admin
from .models import Farmer, Buyer



# Register your models here.

class FarmerAdmin(admin.ModelAdmin):
    list_display = ['name', 'crop_type', 'crop_name', 'price', 'location', 'farm_size', 'quality', 'quantity', 'date_posted', 'phone_number', 'ration_card_number']
    search_fields = ['name', 'crop_type', 'crop_name']
    list_filter = ['crop_type', 'location', 'date_posted']


class BuyerAdmin(admin.ModelAdmin):
    list_display = ['name', 'crop_type', 'quantity', 'budget']
    search_fields = ['name', 'crop_type']
    list_filter = ['crop_type']

admin.site.register(Farmer, FarmerAdmin)
admin.site.register(Buyer, BuyerAdmin)

