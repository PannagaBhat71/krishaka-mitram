from django import forms
from .models import Farmer, Buyer

class Farmerform(forms.ModelForm):
    class Meta:
        model = Farmer
        fields = ['name', 'crop_type', 'crop_name', 'price', 'location', 'farm_size', 'quality', 'quantity', 'phone_number', 'ration_card_number']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter farmer / farm name'}),
            'crop_type': forms.Select(attrs={'class': 'form-select'}),
            'crop_name': forms.Select(attrs={'class': 'form-select'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Price in ₹ (per quintal/kg)', 'step': '0.01'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Location / Taluk (e.g. Bantwal, Puttur, Udupi)'}),
            'farm_size': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Farm size in acres', 'step': '0.01'}),
            'quality': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Quality grade (1 - 10)', 'step': '0.1', 'min': '1', 'max': '10'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Quantity in quintals', 'step': '0.01'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Mobile number'}),
            'ration_card_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ration card number'}),
        }
        labels = {
            'name': 'Farmer Name / Farm Title',
            'crop_type': 'Crop Category',
            'crop_name': 'Crop Name',
            'price': 'Expected Price (₹)',
            'location': 'Location / Taluk',
            'farm_size': 'Farm Size (Acres)',
            'quality': 'Quality Grade (1-10)',
            'quantity': 'Quantity Available (Quintals)',
            'phone_number': 'Phone / WhatsApp Number',
            'ration_card_number': 'Ration Card Number',
        }