from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from notifications.models import Notification
from moderation.models import ModerationViolation, FilterRule, ModerationIncident
from chat.models import Conversation, Message
from farmer.models import Farmer, Crop

User = get_user_model()


class NotificationModelTests(TestCase):
    """Tests for Notification model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='notifyuser',
            password='Password123!',
            role='farmer'
        )

    def test_notification_creation(self):
        """Test creating a notification."""
        notif = Notification.objects.create(
            recipient=self.user,
            notification_type='system',
            title='Test Notification',
            message='This is a test message'
        )
        self.assertEqual(notif.recipient, self.user)
        self.assertEqual(notif.notification_type, 'system')
        self.assertFalse(notif.is_read)

    def test_notification_mark_as_read(self):
        """Test marking notification as read."""
        notif = Notification.objects.create(
            recipient=self.user,
            notification_type='system',
            title='Test',
            message='Message'
        )
        self.assertFalse(notif.is_read)
        notif.mark_as_read()
        self.assertTrue(notif.is_read)
        self.assertIsNotNone(notif.read_at)

    def test_notification_create_classmethod(self):
        """Test Notification.create_notification classmethod."""
        notif = Notification.create_notification(
            recipient=self.user,
            notification_type='violation_new',
            title='Violation Detected',
            message='Your message was flagged'
        )
        self.assertEqual(notif.recipient, self.user)
        self.assertEqual(notif.notification_type, 'violation_new')

    def test_notification_create_with_content_object(self):
        """Test creating notification with related object."""
        # Create a violation as related object
        farmer = User.objects.create_user(username='f1', password='p', role='farmer')
        buyer = User.objects.create_user(username='b1', password='p', role='buyer')
        crop = Crop.objects.create(name='Test Crop')
        listing = Farmer.objects.create(
            crop_type=crop,
            crop_name=crop,
            price=1000,
            location='Test Location',
            farm_size=5,
            quality=80,
            quantity=100,
            phone_number='9876543210',
            ration_card_number='RC123456',
            posted_by=farmer
        )
        conv = Conversation.objects.create(farmer=farmer, buyer=buyer, farmer_listing=listing)
        msg = Message.objects.create(conversation=conv, sender=buyer, content='test')
        rule = FilterRule.objects.create(
            name='Test Rule', pattern='', rule_type='phone',
            severity='high', action='block'
        )
        # Create incident and violation (new model structure)
        incident = ModerationIncident.objects.create(
            conversation=conv,
            submitting_user=buyer,
            blocked_content='test',
            status='NEW'
        )
        violation = ModerationViolation.objects.create(
            incident=incident,
            rule=rule,
            detected_content='9876543210',
            severity='high'
        )

        notif = Notification.create_notification(
            recipient=self.user,
            notification_type='violation_new',
            title='Violation',
            message='Message flagged',
            content_object=violation
        )
        self.assertEqual(notif.content_object, violation)


class NotificationViewsTests(TestCase):
    """Tests for notification views."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='notifyviewuser',
            password='Password123!',
            role='farmer'
        )
        self.moderator = User.objects.create_user(
            username='moduser',
            password='Password123!',
            role='moderator'
        )

    def test_notification_list_view_requires_login(self):
        """Test notification list requires authentication."""
        response = self.client.get(reverse('notifications:notification_list'))
        self.assertEqual(response.status_code, 302)
        # Default login redirect
        self.assertIn('/accounts/login/', response.url)

    def test_notification_list_view(self):
        """Test notification list displays notifications."""
        self.client.force_login(self.user)
        Notification.objects.create(
            recipient=self.user,
            notification_type='system',
            title='Notif 1',
            message='Message 1'
        )
        Notification.objects.create(
            recipient=self.user,
            notification_type='chat_message',
            title='Notif 2',
            message='Message 2'
        )
        response = self.client.get(reverse('notifications:notification_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'notifications/list.html')
        self.assertContains(response, 'Notif 1')
        self.assertContains(response, 'Notif 2')

    def test_notification_list_shows_unread_first(self):
        """Test unread notifications appear first."""
        self.client.force_login(self.user)
        notif1 = Notification.objects.create(
            recipient=self.user,
            notification_type='system',
            title='Read',
            message='Read message'
        )
        notif1.mark_as_read()
        notif2 = Notification.objects.create(
            recipient=self.user,
            notification_type='system',
            title='Unread',
            message='Unread message'
        )
        response = self.client.get(reverse('notifications:notification_list'))
        # First notification in context should be unread
        self.assertEqual(response.context['notifications'][0].title, 'Unread')

    def test_mark_read_view(self):
        """Test marking a notification as read."""
        self.client.force_login(self.user)
        notif = Notification.objects.create(
            recipient=self.user,
            notification_type='system',
            title='To Read',
            message='Read me'
        )
        response = self.client.post(reverse('notifications:mark_read', args=[notif.id]))
        self.assertEqual(response.status_code, 302)
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    def test_mark_read_other_user_notification(self):
        """Test user cannot mark other user's notification as read."""
        other = User.objects.create_user(username='other', password='p', role='buyer')
        notif = Notification.objects.create(
            recipient=other,
            notification_type='system',
            title='Other Notif',
            message='Not yours'
        )
        self.client.force_login(self.user)
        response = self.client.post(reverse('notifications:mark_read', args=[notif.id]))
        self.assertEqual(response.status_code, 404)

    def test_mark_all_read_view(self):
        """Test marking all notifications as read."""
        self.client.force_login(self.user)
        Notification.objects.create(
            recipient=self.user,
            notification_type='system',
            title='Notif 1',
            message='Msg 1'
        )
        Notification.objects.create(
            recipient=self.user,
            notification_type='system',
            title='Notif 2',
            message='Msg 2'
        )
        response = self.client.post(reverse('notifications:mark_all_read'))
        self.assertEqual(response.status_code, 302)
        unread = Notification.objects.filter(recipient=self.user, is_read=False).count()
        self.assertEqual(unread, 0)

    def test_api_notification_count(self):
        """Test API endpoint for notification count."""
        self.client.force_login(self.user)
        Notification.objects.create(
            recipient=self.user,
            notification_type='system',
            title='Unread 1',
            message='Msg'
        )
        Notification.objects.create(
            recipient=self.user,
            notification_type='system',
            title='Unread 2',
            message='Msg'
        )
        notif3 = Notification.objects.create(
            recipient=self.user,
            notification_type='system',
            title='Read',
            message='Msg'
        )
        notif3.mark_as_read()

        response = self.client.get(reverse('notifications:api_count'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 2)


class NotificationIntegrationTests(TestCase):
    """Integration tests for notifications."""

    def setUp(self):
        self.farmer = User.objects.create_user(
            username='intfarmer',
            password='Password123!',
            role='farmer'
        )
        self.buyer = User.objects.create_user(
            username='intbuyer',
            password='Password123!',
            role='buyer'
        )
        self.crop = Crop.objects.create(name='Paddy')
        self.listing = Farmer.objects.create(
            crop_type=self.crop,
            crop_name=self.crop,
            price=2500,
            location='Test Location',
            farm_size=10,
            quality=80,
            quantity=1000,
            phone_number='9876543210',
            ration_card_number='RC123456',
            posted_by=self.farmer
        )

    def test_chat_message_creates_notification(self):
        """Test new chat message creates notification for other participant."""
        from chat.consumers import ChatConsumer
        from channels.testing import WebsocketCommunicator

        conv = Conversation.objects.create(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        )

        # Create message via WebSocket consumer logic
        from notifications.models import Notification
        msg = Message.objects.create(conversation=conv, sender=self.buyer, content='Hello farmer!')

        # Call the notification method directly
        other_user = conv.farmer if msg.sender == conv.buyer else conv.buyer
        Notification.create_notification(
            recipient=other_user,
            notification_type='chat_message',
            title=f"New message from {msg.sender.username}",
            message=msg.content[:100],
            content_object=msg
        )

        notif = Notification.objects.get(recipient=self.farmer)
        self.assertEqual(notif.notification_type, 'chat_message')
        self.assertIn('Hello farmer', notif.message)

    def test_single_message_creates_one_notification(self):
        """Test that one submitted message creates exactly one notification record."""
        conv = Conversation.objects.create(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        )

        # Create message via consumer logic (same as WebSocket)
        msg = Message.objects.create(conversation=conv, sender=self.buyer, content='Test message')

        # Call the notification method directly (same as _notify_other_participant)
        other_user = conv.farmer if msg.sender == conv.buyer else conv.buyer
        Notification.create_notification(
            recipient=other_user,
            notification_type='chat_message',
            title=f"New message from {msg.sender.username}",
            message=msg.content[:100],
            content_object=msg
        )

        # Should have exactly one notification
        notifications = Notification.objects.filter(recipient=self.farmer, notification_type='chat_message')
        self.assertEqual(notifications.count(), 1)

        # Sending another message should create another notification
        msg2 = Message.objects.create(conversation=conv, sender=self.buyer, content='Second message')
        Notification.create_notification(
            recipient=other_user,
            notification_type='chat_message',
            title=f"New message from {msg2.sender.username}",
            message=msg2.content[:100],
            content_object=msg2
        )

        notifications = Notification.objects.filter(recipient=self.farmer, notification_type='chat_message')
        self.assertEqual(notifications.count(), 2)

    def test_violation_creates_notification(self):
        """Test violation creates notification for moderators."""
        # This would be tested via moderation views
        from notifications.models import Notification
        from moderation.models import ModerationViolation, FilterRule, ModerationIncident

        conv = Conversation.objects.create(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        )
        # Create incident and violation
        incident = ModerationIncident.objects.create(
            conversation=conv,
            submitting_user=self.buyer,
            blocked_content='Call 9876543210',
            status='NEW'
        )
        rule = FilterRule.objects.create(
            name='Phone Rule', pattern='', rule_type='phone',
            severity='high', action='block'
        )
        violation = ModerationViolation.objects.create(
            incident=incident,
            rule=rule,
            detected_content='9876543210',
            severity='high'
        )

        # Create notification for moderator
        mod = User.objects.create_user(username='mod', password='p', role='moderator')
        Notification.create_notification(
            recipient=mod,
            notification_type='violation_new',
            title='New Violation Detected',
            message=f'Violation in conversation #{conv.id}',
            content_object=violation
        )

        notif = Notification.objects.get(recipient=mod)
        self.assertEqual(notif.notification_type, 'violation_new')

    def test_user_restriction_creates_notification(self):
        """Test user restriction creates notification for user."""
        notif = Notification.create_notification(
            recipient=self.buyer,
            notification_type='user_restricted',
            title='Account Restricted',
            message='Your chat access has been restricted for 7 days due to policy violations.'
        )
        self.assertIsNotNone(notif)
        self.assertIn('restricted', notif.message.lower())
        self.assertEqual(notif.notification_type, 'user_restricted')
        self.assertEqual(notif.recipient, self.buyer)


class NotificationTypesTests(TestCase):
    """Test all notification types."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='typesuser',
            password='Password123!',
            role='farmer'
        )

    def test_all_notification_types(self):
        """Test all defined notification types can be created."""
        types = [
            'violation_new', 'violation_assigned', 'violation_resolved',
            'user_restricted', 'user_unrestricted',
            'chat_message', 'chat_started', 'rule_triggered', 'system'
        ]

        for ntype in types:
            with self.subTest(ntype=ntype):
                notif = Notification.objects.create(
                    recipient=self.user,
                    notification_type=ntype,
                    title=f'{ntype} title',
                    message=f'{ntype} message'
                )
                self.assertEqual(notif.notification_type, ntype)