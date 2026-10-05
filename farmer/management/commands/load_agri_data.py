import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from accounts.models import CustomUser
from farmer.models import Crop, Farmer, Buyer

class Command(BaseCommand):
    help = 'Load Karnataka agricultural data from karnataka_agri_data.json into the database'

    def handle(self, *args, **options):
        json_path = settings.BASE_DIR / 'karnataka_agri_data.json'
        if not json_path.exists():
            self.stderr.write(self.style.ERROR(f"File not found: {json_path}"))
            return

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Clear existing entries for a clean reload
        Buyer.objects.all().delete()
        Farmer.objects.all().delete()
        Crop.objects.all().delete()

        # 1. Load Crops
        crop_map = {}
        for item in data:
            if item['model'] == 'myapp.crop':
                c, _ = Crop.objects.update_or_create(
                    id=item['pk'],
                    defaults={'name': item['fields']['name']}
                )
                crop_map[item['pk']] = c

        # 2. Load Users
        user_map = {}
        for item in data:
            if item['model'] == 'auth.user':
                fields = item['fields']
                u, _ = CustomUser.objects.update_or_create(
                    id=item['pk'],
                    defaults={
                        'username': fields['username'],
                        'email': fields.get('email', ''),
                        'is_active': fields.get('is_active', True),
                        'role': 'farmer' if item['pk'] <= 10 else 'buyer'
                    }
                )
                if not u.has_usable_password():
                    u.set_password('Password123!')
                    u.save()
                user_map[item['pk']] = u

        # 3. Load Farmers
        farmer_map = {}
        for item in data:
            if item['model'] == 'myapp.farmer':
                f = item['fields']
                farmer = Farmer.objects.create(
                    id=item['pk'],
                    name=f['name'],
                    crop_type=crop_map.get(f['crop_type']),
                    crop_name=crop_map.get(f['crop_name']),
                    price=f['price'],
                    location=f['location'],
                    farm_size=f['farm_size'],
                    quality=f['quality'],
                    quantity=f['quantity'],
                    date_posted=f['date_posted'],
                    phone_number=f['phone_number'],
                    ration_card_number=f['ration_card_number'],
                    posted_by=user_map.get(f.get('posted_by'))
                )
                farmer_map[item['pk']] = farmer

        # 4. Load Buyers
        for item in data:
            if item['model'] == 'myapp.buyer':
                b = item['fields']
                Buyer.objects.create(
                    id=item['pk'],
                    Farmer=farmer_map.get(b.get('Farmer')),
                    Buyer=user_map.get(b.get('Buyer')),
                    name=b.get('name', ''),
                    crop_type=crop_map.get(b.get('crop_type')),
                    quantity=b.get('quantity'),
                    budget=b.get('budget'),
                    message=b.get('message', ''),
                    date_applied=b.get('date_applied')
                )

        self.stdout.write(self.style.SUCCESS(
            f"Successfully loaded {Crop.objects.count()} crops, {CustomUser.objects.count()} users, "
            f"{Farmer.objects.count()} farmer listings, and {Buyer.objects.count()} buyer records."
        ))
