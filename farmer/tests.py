from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from farmer.models import Crop, Farmer, Buyer

User = get_user_model()

class KrishakaMitramTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.farmer_user = User.objects.create_user(
            username='ramesh_farmer',
            password='Password123!',
            email='ramesh@example.com',
            role='farmer'
        )
        self.buyer_user = User.objects.create_user(
            username='suresh_buyer',
            password='Password123!',
            email='suresh@example.com',
            role='buyer'
        )
        self.crop_category = Crop.objects.create(name='Plantation Crop')
        self.crop_produce = Crop.objects.create(name='Arecanut (Adike)')

        self.farmer_listing = Farmer.objects.create(
            name='Ramesh Poojary',
            crop_type=self.crop_category,
            crop_name=self.crop_produce,
            price=450.00,
            location='Bantwal, Dakshina Kannada',
            farm_size=3.5,
            quality=9.0,
            quantity=25.0,
            phone_number='9876543210',
            ration_card_number='RC987654321',
            posted_by=self.farmer_user
        )

    def test_home_and_farmer_list_views(self):
        # Test home view (/)
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Krishaka Mitram')
        self.assertContains(response, 'Arecanut (Adike)')
        self.assertTemplateUsed(response, 'farmer/farmer_list.html')

        # Test farmer-list view (/farmers/)
        response_list = self.client.get(reverse('farmer-list'))
        self.assertEqual(response_list.status_code, 200)

        # Test search query
        response_search = self.client.get(reverse('farmer-list') + '?q=Bantwal')
        self.assertEqual(response_search.status_code, 200)
        self.assertContains(response_search, 'Ramesh Poojary')

    def test_farmer_detail_view(self):
        url = reverse('farmer-detail', kwargs={'pk': self.farmer_listing.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ramesh Poojary')
        self.assertContains(response, '9876543210')
        self.assertContains(response, 'Bantwal, Dakshina Kannada')
        self.assertTemplateUsed(response, 'farmer/farmer_detail.html')

    def test_farmer_create_view_requires_login(self):
        url = reverse('farmer-create')
        # Anonymous should redirect to login
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

        # Logged in farmer can view form
        self.client.login(username='ramesh_farmer', password='Password123!')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'farmer/farmer_form.html')

        # Create new listing
        post_data = {
            'name': 'Ramesh Poojary',
            'crop_type': self.crop_category.pk,
            'crop_name': self.crop_produce.pk,
            'price': '500.00',
            'location': 'Puttur',
            'farm_size': '2.0',
            'quality': '8.5',
            'quantity': '15.0',
            'phone_number': '9876543210',
            'ration_card_number': 'RC11223344',
        }
        create_resp = self.client.post(url, post_data)
        self.assertEqual(create_resp.status_code, 302)
        self.assertTrue(Farmer.objects.filter(location='Puttur').exists())

    def test_farmer_update_and_delete_permissions(self):
        update_url = reverse('farmer-update', kwargs={'pk': self.farmer_listing.pk})
        delete_url = reverse('farmer-delete', kwargs={'pk': self.farmer_listing.pk})

        # Buyer should be forbidden (403) from updating/deleting Ramesh's listing
        self.client.login(username='suresh_buyer', password='Password123!')
        self.assertEqual(self.client.get(update_url).status_code, 403)
        self.assertEqual(self.client.get(delete_url).status_code, 403)

        # Owner can view update and delete forms
        self.client.login(username='ramesh_farmer', password='Password123!')
        self.assertEqual(self.client.get(update_url).status_code, 200)
        self.assertEqual(self.client.get(delete_url).status_code, 200)

        # Perform update
        post_data = {
            'name': 'Ramesh Poojary Updated',
            'crop_type': self.crop_category.pk,
            'crop_name': self.crop_produce.pk,
            'price': '480.00',
            'location': 'Bantwal, Dakshina Kannada',
            'farm_size': '3.5',
            'quality': '9.0',
            'quantity': '20.0',
            'phone_number': '9876543210',
            'ration_card_number': 'RC987654321',
        }
        self.client.post(update_url, post_data)
        self.farmer_listing.refresh_from_db()
        self.assertEqual(self.farmer_listing.name, 'Ramesh Poojary Updated')

    def test_buyer_inquiry_flow(self):
        inquire_url = reverse('apply-job', kwargs={'pk': self.farmer_listing.pk})

        # Owner cannot inquire about their own listing
        self.client.login(username='ramesh_farmer', password='Password123!')
        resp = self.client.get(inquire_url, follow=True)
        self.assertContains(resp, 'You cannot send a buyer inquiry for your own produce listing')

        # Buyer can inquire
        self.client.login(username='suresh_buyer', password='Password123!')
        resp = self.client.get(inquire_url, follow=True)
        self.assertContains(resp, 'Inquiry sent!')
        self.assertTrue(Buyer.objects.filter(Farmer=self.farmer_listing, Buyer=self.buyer_user).exists())

        # Inquiries view for buyer
        my_inquiries_url = reverse('my-applications')
        inq_resp = self.client.get(my_inquiries_url)
        self.assertEqual(inq_resp.status_code, 200)
        self.assertContains(inq_resp, 'Arecanut (Adike)')
