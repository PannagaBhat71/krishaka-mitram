from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from channels.testing import WebsocketCommunicator
from chat.models import Conversation, Message
from farmer.models import Farmer, Crop
from moderation.filters import message_filter_engine
from moderation.models import ModerationViolation, FilterRule, ModerationIncident
from notifications.models import Notification
from audit.models import AuditLog

User = get_user_model()


class ChatModelsTests(TestCase):
    """Tests for chat models."""

    def setUp(self):
        self.farmer = User.objects.create_user(
            username='testfarmer',
            password='Password123!',
            role='farmer'
        )
        self.buyer = User.objects.create_user(
            username='testbuyer',
            password='Password123!',
            role='buyer'
        )
        self.crop = Crop.objects.create(name='Paddy')
        self.listing = Farmer.objects.create(
            name='Test Farmer',
            crop_type=self.crop,
            crop_name=self.crop,
            price=2500,
            location='Bangalore',
            farm_size=10,
            quality=80,
            quantity=1000,
            phone_number='9876543210',
            ration_card_number='RC123456',
            posted_by=self.farmer
        )

    def test_conversation_creation(self):
        """Test creating a conversation between farmer and buyer."""
        conv = Conversation.objects.create(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        )
        self.assertEqual(conv.farmer, self.farmer)
        self.assertEqual(conv.buyer, self.buyer)
        self.assertTrue(conv.is_active)

    def test_conversation_close(self):
        """Test closing a conversation."""
        conv = Conversation.objects.create(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        )
        conv.close(self.buyer)
        self.assertFalse(conv.is_active)
        self.assertEqual(conv.closed_by, self.buyer)

    def test_message_creation(self):
        """Test creating a message."""
        conv = Conversation.objects.create(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        )
        msg = Message.objects.create(
            conversation=conv,
            sender=self.buyer,
            content='Hello farmer!'
        )
        self.assertEqual(msg.sender, self.buyer)
        self.assertFalse(msg.is_filtered)

    def test_message_soft_delete(self):
        """Test soft deleting a message."""
        conv = Conversation.objects.create(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        )
        msg = Message.objects.create(
            conversation=conv,
            sender=self.buyer,
            content='Hello'
        )
        msg.soft_delete(self.buyer)
        self.assertTrue(msg.is_deleted)
        self.assertEqual(msg.deleted_by, self.buyer)


class ChatViewsTests(TestCase):
    """Tests for chat views."""

    def setUp(self):
        self.client = Client()
        self.farmer = User.objects.create_user(
            username='farmer1',
            password='Password123!',
            role='farmer'
        )
        self.buyer = User.objects.create_user(
            username='buyer1',
            password='Password123!',
            role='buyer'
        )
        self.crop = Crop.objects.create(name='Wheat')
        self.listing = Farmer.objects.create(
            name='Farmer One',
            crop_type=self.crop,
            crop_name=self.crop,
            price=2200,
            location='Mysore',
            farm_size=5,
            quality=90,
            quantity=500,
            phone_number='9876543211',
            ration_card_number='RC654321',
            posted_by=self.farmer
        )

    def test_chat_login_view_get(self):
        """Test chat login page loads."""
        response = self.client.get(reverse('chat:chat_login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'chat/login.html')

    def test_chat_login_view_post_success(self):
        """Test successful chat login."""
        response = self.client.post(reverse('chat:chat_login'), {
            'username': 'farmer1',
            'password': 'Password123!'
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('chat:chat_list'))

    def test_chat_login_view_post_invalid(self):
        """Test chat login with invalid credentials."""
        response = self.client.post(reverse('chat:chat_login'), {
            'username': 'farmer1',
            'password': 'WrongPassword'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid username or password')

    def test_chat_logout_view(self):
        """Test chat logout."""
        self.client.force_login(self.buyer)
        response = self.client.get(reverse('chat:chat_logout'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('chat:chat_login'))

    def test_chat_list_view_requires_login(self):
        """Test chat list requires authentication."""
        response = self.client.get(reverse('chat:chat_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_chat_list_view_as_buyer(self):
        """Test chat list for buyer with conversations."""
        self.client.force_login(self.buyer)
        conv = Conversation.objects.create(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        )
        response = self.client.get(reverse('chat:chat_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'chat/chat_list.html')

    def test_start_chat_view_requires_buyer_role(self):
        """Test only buyers can start chats."""
        self.client.force_login(self.farmer)
        response = self.client.get(reverse('chat:start_chat', args=[self.listing.id]))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('farmer-detail', args=[self.listing.id]))

    def test_start_chat_view_creates_conversation(self):
        """Test starting a new chat creates conversation."""
        self.client.force_login(self.buyer)
        response = self.client.get(reverse('chat:start_chat', args=[self.listing.id]))
        self.assertEqual(response.status_code, 302)
        conv = Conversation.objects.get(farmer=self.farmer, buyer=self.buyer)
        self.assertRedirects(response, reverse('chat:chat_detail', args=[conv.id]))

    def test_chat_detail_view_requires_participant(self):
        """Test chat detail only accessible to participants."""
        other_buyer = User.objects.create_user(
            username='buyer2',
            password='Password123!',
            role='buyer'
        )
        self.client.force_login(other_buyer)
        conv = Conversation.objects.create(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        )
        response = self.client.get(reverse('chat:chat_detail', args=[conv.id]))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('chat:chat_list'))

    def test_send_message_view_ajax(self):
        """Test sending message via AJAX."""
        self.client.force_login(self.buyer)
        conv = Conversation.objects.create(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        )
        response = self.client.post(
            reverse('chat:send_message', args=[conv.id]),
            {'content': 'Hello farmer!'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['id'])
        self.assertEqual(response.json()['content'], 'Hello farmer!')
        self.assertFalse(response.json()['is_filtered'])

    
def test_send_message_view_allows_phone_and_records_violation(self):
    """Filtered messages are allowed and logged for moderation."""
    self.client.force_login(self.buyer)
    conv = Conversation.objects.create(
        farmer=self.farmer,
        buyer=self.buyer,
        farmer_listing=self.listing,
    )

    response = self.client.post(
        reverse('chat:send_message', args=[conv.id]),
        {'content': 'Call me at 9876543210'},
        HTTP_X_REQUESTED_WITH='XMLHttpRequest',
    )

    self.assertEqual(response.status_code, 200)
    self.assertTrue(response.json()['id'])

    message = Message.objects.get(id=response.json()['id'])
    self.assertEqual(message.sender, self.buyer)
    self.assertTrue(message.is_filtered)

    incident = ModerationIncident.objects.get(message=message)
    self.assertEqual(incident.conversation, conv)
    self.assertEqual(incident.submitting_user, self.buyer)

    violation = ModerationViolation.objects.filter(
        incident=incident
    ).first()
    self.assertIsNotNone(violation)


    def test_close_conversation_view(self):
        """Test closing a conversation."""
        self.client.force_login(self.buyer)
        conv = Conversation.objects.create(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        )
        response = self.client.post(reverse('chat:close_conversation', args=[conv.id]))
        self.assertEqual(response.status_code, 302)
        conv.refresh_from_db()
        self.assertFalse(conv.is_active)


class ChatConsumerTests(TestCase):
    """Tests for WebSocket chat consumer."""

    async def test_consumer_connect_requires_auth(self):
        """Test consumer rejects unauthenticated connections."""
        from chat.consumers import ChatConsumer
        from channels.testing import WebsocketCommunicator

        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(),
            '/ws/chat/1/'
        )
        communicator.scope['url_route'] = {'kwargs': {'conversation_id': 1}}
        connected, _ = await communicator.connect()
        self.assertFalse(connected)

    async def test_consumer_connect_participant_only(self):
        """Test consumer rejects non-participants."""
        from chat.consumers import ChatConsumer
        from channels.testing import WebsocketCommunicator
        from asgiref.sync import sync_to_async

        farmer = await sync_to_async(User.objects.create_user)(
            username='wscfarmer',
            password='Password123!',
            role='farmer'
        )
        buyer = await sync_to_async(User.objects.create_user)(
            username='wscbuyer',
            password='Password123!',
            role='buyer'
        )
        other = await sync_to_async(User.objects.create_user)(
            username='wsother',
            password='Password123!',
            role='buyer'
        )
        crop = await sync_to_async(Crop.objects.create)(name='Test')
        listing = await sync_to_async(Farmer.objects.create)(
            name='WS Farmer',
            crop_type=crop,
            crop_name=crop,
            price=1000,
            location='Test Location',
            farm_size=1,
            quality=50,
            quantity=100,
            phone_number='9876543212',
            ration_card_number='RC999999',
            posted_by=farmer
        )
        conv = await sync_to_async(Conversation.objects.create)(
            farmer=farmer,
            buyer=buyer,
            farmer_listing=listing
        )

        # Test non-participant rejected
        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(),
            f'/ws/chat/{conv.id}/',
        )
        communicator.scope['user'] = other
        communicator.scope['url_route'] = {'kwargs': {'conversation_id': conv.id}}
        connected, _ = await communicator.connect()
        self.assertFalse(connected)

    async def test_consumer_send_message(self):
        """Test sending message through WebSocket."""
        from chat.consumers import ChatConsumer
        from channels.testing import WebsocketCommunicator
        from asgiref.sync import sync_to_async

        farmer = await sync_to_async(User.objects.create_user)(
            username='wsfarmer',
            password='Password123!',
            role='farmer'
        )
        buyer = await sync_to_async(User.objects.create_user)(
            username='wsbuyer',
            password='Password123!',
            role='buyer'
        )
        crop = await sync_to_async(Crop.objects.create)(name='Test')
        listing = await sync_to_async(Farmer.objects.create)(
            name='WS Farmer 2',
            crop_type=crop,
            crop_name=crop,
            price=1000,
            location='Test Location 2',
            farm_size=1,
            quality=50,
            quantity=100,
            phone_number='9876543213',
            ration_card_number='RC888888',
            posted_by=farmer
        )
        conv = await sync_to_async(Conversation.objects.create)(
            farmer=farmer,
            buyer=buyer,
            farmer_listing=listing
        )

        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(),
            f'/ws/chat/{conv.id}/',
        )
        communicator.scope['user'] = buyer
        communicator.scope['url_route'] = {'kwargs': {'conversation_id': conv.id}}
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Receive connection_established message
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'connection_established')

        # Send message
        await communicator.send_json_to({
            'type': 'message',
            'content': 'Hello via WebSocket!'
        })

        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'chat_message')
        self.assertEqual(response['sender_username'], 'wsbuyer')
        self.assertEqual(response['content'], 'Hello via WebSocket!')

        await communicator.disconnect()

    async def test_consumer_allows_phone_and_records_violation(self):
        """Test WebSocket blocks messages with phone numbers."""
        from chat.consumers import ChatConsumer
        from channels.testing import WebsocketCommunicator
        from asgiref.sync import sync_to_async

        farmer = await sync_to_async(User.objects.create_user)(
            username='wsfarmer2',
            password='Password123!',
            role='farmer'
        )
        buyer = await sync_to_async(User.objects.create_user)(
            username='wsbuyer2',
            password='Password123!',
            role='buyer'
        )
        crop = await sync_to_async(Crop.objects.create)(name='Test')
        listing = await sync_to_async(Farmer.objects.create)(
            name='WS Farmer 3',
            crop_type=crop,
            crop_name=crop,
            price=1000,
            location='Test Location 3',
            farm_size=1,
            quality=50,
            quantity=100,
            phone_number='9876543214',
            ration_card_number='RC777777',
            posted_by=farmer
        )
        conv = await sync_to_async(Conversation.objects.create)(
            farmer=farmer,
            buyer=buyer,
            farmer_listing=listing
        )

        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(),
            f'/ws/chat/{conv.id}/',
        )
        communicator.scope['user'] = buyer
        communicator.scope['url_route'] = {'kwargs': {'conversation_id': conv.id}}
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Receive connection_established message
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'connection_established')

        # Send message with phone
        await communicator.send_json_to({
            'type': 'message',
            'content': 'My number is 9876543210'
        })

        response = await communicator.receive_json_from()
        
        self.assertEqual(response['type'], 'chat_message')
        self.assertTrue(response['is_filtered'])
        self.assertTrue(response.get('message_id'))

        message = await sync_to_async(Message.objects.get)(
            id=response['message_id']
        )
        self.assertTrue(message.is_filtered)

        incident = await sync_to_async(
            lambda: ModerationIncident.objects.get(message=message)
        )()
        self.assertEqual(incident.submitting_user_id, buyer.id)

        violation_exists = await sync_to_async(
            lambda: ModerationViolation.objects.filter(
                incident=incident
            ).exists()
        )()
        self.assertTrue(violation_exists)

        await communicator.disconnect()


    async def test_consumer_allows_clean_message(self):
        """Test WebSocket allows clean messages through."""
        from chat.consumers import ChatConsumer
        from channels.testing import WebsocketCommunicator
        from asgiref.sync import sync_to_async

        farmer = await sync_to_async(User.objects.create_user)(
            username='wsfarmer_clean',
            password='Password123!',
            role='farmer'
        )
        buyer = await sync_to_async(User.objects.create_user)(
            username='wsbuyer_clean',
            password='Password123!',
            role='buyer'
        )
        crop = await sync_to_async(Crop.objects.create)(name='Test')
        listing = await sync_to_async(Farmer.objects.create)(
            name='WS Farmer Clean',
            crop_type=crop,
            crop_name=crop,
            price=1000,
            location='Test Location Clean',
            farm_size=1,
            quality=50,
            quantity=100,
            phone_number='9876543215',
            ration_card_number='RC666666',
            posted_by=farmer
        )
        conv = await sync_to_async(Conversation.objects.create)(
            farmer=farmer,
            buyer=buyer,
            farmer_listing=listing
        )

        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(),
            f'/ws/chat/{conv.id}/',
        )
        communicator.scope['user'] = buyer
        communicator.scope['url_route'] = {'kwargs': {'conversation_id': conv.id}}
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Receive connection_established message
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'connection_established')

        # Send clean message
        await communicator.send_json_to({
            'type': 'message',
            'content': 'Hello, interested in your produce'
        })

        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'chat_message')
        self.assertEqual(response['content'], 'Hello, interested in your produce')
        self.assertFalse(response['is_filtered'])

        # Verify Message was created
        message_count = await sync_to_async(Message.objects.count)()
        self.assertEqual(message_count, 1)

        await communicator.disconnect()

    async def test_consumer_typing_indicator(self):
        """Test typing indicator broadcast."""
        from chat.consumers import ChatConsumer
        from channels.testing import WebsocketCommunicator
        from asgiref.sync import sync_to_async

        farmer = await sync_to_async(User.objects.create_user)(
            username='wsfarmer3',
            password='Password123!',
            role='farmer'
        )
        buyer = await sync_to_async(User.objects.create_user)(
            username='wsbuyer3',
            password='Password123!',
            role='buyer'
        )
        crop = await sync_to_async(Crop.objects.create)(name='Test')
        listing = await sync_to_async(Farmer.objects.create)(
            name='WS Farmer 4',
            crop_type=crop,
            crop_name=crop,
            price=1000,
            location='Test Location 4',
            farm_size=1,
            quality=50,
            quantity=100,
            phone_number='9876543215',
            ration_card_number='RC666666',
            posted_by=farmer
        )
        conv = await sync_to_async(Conversation.objects.create)(
            farmer=farmer,
            buyer=buyer,
            farmer_listing=listing
        )

        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(),
            f'/ws/chat/{conv.id}/',
        )
        communicator.scope['user'] = buyer
        communicator.scope['url_route'] = {'kwargs': {'conversation_id': conv.id}}
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Receive connection_established message
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'connection_established')

        # Send typing indicator
        await communicator.send_json_to({
            'type': 'typing',
            'is_typing': True
        })

        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'user_typing')
        self.assertEqual(response['user_id'], buyer.id)
        self.assertTrue(response['is_typing'])

        await communicator.disconnect()


    async def test_consumer_clean_message_no_badge(self):
        """Test that clean messages like 'hi' do not show filtered badge."""
        from chat.consumers import ChatConsumer
        from channels.testing import WebsocketCommunicator
        from asgiref.sync import sync_to_async

        farmer = await sync_to_async(User.objects.create_user)(
            username='wsfarmer_clean2',
            password='Password123!',
            role='farmer'
        )
        buyer = await sync_to_async(User.objects.create_user)(
            username='wsbuyer_clean2',
            password='Password123!',
            role='buyer'
        )
        crop = await sync_to_async(Crop.objects.create)(name='Test')
        listing = await sync_to_async(Farmer.objects.create)(
            name='WS Farmer Clean 2',
            crop_type=crop,
            crop_name=crop,
            price=1000,
            location='Test Location Clean 2',
            farm_size=1,
            quality=50,
            quantity=100,
            phone_number='9876543215',
            ration_card_number='RC666666',
            posted_by=farmer
        )
        conv = await sync_to_async(Conversation.objects.create)(
            farmer=farmer,
            buyer=buyer,
            farmer_listing=listing
        )

        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(),
            f'/ws/chat/{conv.id}/',
        )
        communicator.scope['user'] = buyer
        communicator.scope['url_route'] = {'kwargs': {'conversation_id': conv.id}}
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Receive connection_established message
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'connection_established')

        # Send clean message "hi"
        await communicator.send_json_to({
            'type': 'message',
            'content': 'hi'
        })

        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'chat_message')
        self.assertEqual(response['content'], 'hi')
        self.assertFalse(response['is_filtered'])

        # Verify Message was created with is_filtered=False
        message = await sync_to_async(Message.objects.get)(id=response['message_id'])
        self.assertFalse(message.is_filtered)
        self.assertEqual(message.filter_types, [])

        await communicator.disconnect()

    async def test_consumer_filtered_message_shows_badge(self):
        """Test that messages with phone numbers show filtered badge."""
        from chat.consumers import ChatConsumer
        from channels.testing import WebsocketCommunicator
        from asgiref.sync import sync_to_async

        farmer = await sync_to_async(User.objects.create_user)(
            username='wsfarmer_filtered',
            password='Password123!',
            role='farmer'
        )
        buyer = await sync_to_async(User.objects.create_user)(
            username='wsbuyer_filtered',
            password='Password123!',
            role='buyer'
        )
        crop = await sync_to_async(Crop.objects.create)(name='Test')
        listing = await sync_to_async(Farmer.objects.create)(
            name='WS Farmer Filtered',
            crop_type=crop,
            crop_name=crop,
            price=1000,
            location='Test Location Filtered',
            farm_size=1,
            quality=50,
            quantity=100,
            phone_number='9876543215',
            ration_card_number='RC666666',
            posted_by=farmer
        )
        conv = await sync_to_async(Conversation.objects.create)(
            farmer=farmer,
            buyer=buyer,
            farmer_listing=listing
        )

        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(),
            f'/ws/chat/{conv.id}/',
        )
        communicator.scope['user'] = buyer
        communicator.scope['url_route'] = {'kwargs': {'conversation_id': conv.id}}
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # Receive connection_established message
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'connection_established')

        # Send message with phone number
        await communicator.send_json_to({
            'type': 'message',
            'content': 'Call me at 9876543210'
        })

        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'chat_message')
        self.assertTrue(response['is_filtered'])
        self.assertIn('phone', response.get('filter_types', []))

        # Verify Message was created with is_filtered=True
        message = await sync_to_async(Message.objects.get)(id=response['message_id'])
        self.assertTrue(message.is_filtered)
        self.assertIn('phone', message.filter_types)

        await communicator.disconnect()


class MessageFilteringIntegrationTests(TestCase):
    """Integration tests for message filtering in chat."""

    def setUp(self):
        self.farmer = User.objects.create_user(
            username='filterfarmer',
            password='Password123!',
            role='farmer'
        )
        self.buyer = User.objects.create_user(
            username='filterbuyer',
            password='Password123!',
            role='buyer'
        )
        self.crop = Crop.objects.create(name='Maize')
        self.listing = Farmer.objects.create(
            name='Filter Farmer',
            crop_type=self.crop,
            crop_name=self.crop,
            price=1800,
            location='Filter Location',
            farm_size=20,
            quality=70,
            quantity=2000,
            phone_number='9876543216',
            ration_card_number='RC111111',
            posted_by=self.farmer
        )

    def test_filter_creates_violation_records(self):
        """Test that filtered messages create violation records."""
        conv = Conversation.objects.create(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        )

        filter_result = message_filter_engine.filter_message('Contact me at 9876543210')

        message = Message.objects.create(
            conversation=conv,
            sender=self.buyer,
            content=filter_result.filtered_content,
            is_filtered=not filter_result.is_clean,
            filter_types=filter_result.filter_types
        )

        # Create incident and violations (new model structure)
        incident = ModerationIncident.objects.create(
            conversation=conv,
            submitting_user=self.buyer,
            message=message,
            blocked_content='',
            status='NEW'
        )

        # Create violations
        db_rules = list(FilterRule.objects.filter(is_active=True, rule_type__in=filter_result.filter_types))
        rule_map = {r.rule_type: r for r in db_rules}

        for violation in filter_result.violations:
            rule = rule_map.get(violation.rule_type)
            if not rule:
                rule, _ = FilterRule.objects.get_or_create(
                    name=f"Auto: {violation.rule_name}",
                    defaults={
                        'pattern': '',
                        'rule_type': violation.rule_type,
                        'severity': violation.severity,
                        'action': violation.action,
                        'description': f"Auto-created rule for {violation.rule_type} detection"
                    }
                )
            ModerationViolation.objects.create(
                incident=incident,
                rule=rule,
                detected_content=violation.detected_text,
                severity=violation.severity
            )

        violations = ModerationViolation.objects.filter(incident=incident)
        self.assertEqual(violations.count(), 1)
        self.assertEqual(violations.first().rule.rule_type, 'phone')

    def test_multiple_violations_single_message(self):
        """Test message with multiple violation types."""
        filter_result = message_filter_engine.filter_message(
            'Phone: 9876543210, Email: test@example.com, UPI: user@paytm'
        )

        self.assertIn('phone', filter_result.filter_types)
        self.assertIn('email', filter_result.filter_types)
        self.assertIn('upi', filter_result.filter_types)
        self.assertTrue(filter_result.should_block)


class FarmerBuyerChatIntegrationTests(TestCase):
    """Tests for farmer-buyer chat integration via inquiries."""

    def setUp(self):
        self.client = Client()
        self.farmer = User.objects.create_user(
            username='farmer_integration',
            password='Password123!',
            role='farmer'
        )
        self.buyer = User.objects.create_user(
            username='buyer_integration',
            password='Password123!',
            role='buyer'
        )
        self.crop = Crop.objects.create(name='Ragi')
        self.listing = Farmer.objects.create(
            name='Integration Farmer',
            crop_type=self.crop,
            crop_name=self.crop,
            price=2000,
            location='Mangalore',
            farm_size=3,
            quality=85,
            quantity=300,
            phone_number='9876543217',
            ration_card_number='RC222222',
            posted_by=self.farmer
        )
        # Create an inquiry from buyer to farmer
        from farmer.models import Buyer as Inquiry
        self.inquiry = Inquiry.objects.create(
            Farmer=self.listing,
            Buyer=self.buyer,
            name='Integration Buyer',
            crop_type=self.crop,
            quantity=10,
            budget=20000,
            message='Interested in your produce'
        )

    def test_farmer_can_start_chat_with_buyer_from_inquiry(self):
        """Test farmer can start conversation with buyer who inquired."""
        self.client.force_login(self.farmer)
        response = self.client.get(reverse('chat:start_chat_with_buyer', args=[self.inquiry.id]))

        # Should redirect to chat detail
        self.assertEqual(response.status_code, 302)
        conversation = Conversation.objects.filter(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        ).first()
        self.assertIsNotNone(conversation)
        self.assertRedirects(response, reverse('chat:chat_detail', args=[conversation.id]))

    def test_farmer_chat_reuses_existing_conversation(self):
        """Test that existing conversation is reused for same buyer-farmer-listing."""
        self.client.force_login(self.farmer)

        # Start chat first time
        response1 = self.client.get(reverse('chat:start_chat_with_buyer', args=[self.inquiry.id]))
        conv1 = Conversation.objects.get(farmer=self.farmer, buyer=self.buyer)

        # Start chat second time
        response2 = self.client.get(reverse('chat:start_chat_with_buyer', args=[self.inquiry.id]))
        conv2 = Conversation.objects.get(farmer=self.farmer, buyer=self.buyer)

        # Should be the same conversation
        self.assertEqual(conv1.id, conv2.id)
        self.assertRedirects(response2, reverse('chat:chat_detail', args=[conv1.id]))

    def test_buyer_cannot_start_chat_with_buyer_view(self):
        """Test buyer cannot use the farmer's start_chat_with_buyer view."""
        self.client.force_login(self.buyer)
        response = self.client.get(reverse('chat:start_chat_with_buyer', args=[self.inquiry.id]))

        # Should redirect to farmer detail with error
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('farmer-detail', args=[self.listing.id]))

    def test_other_farmer_cannot_start_chat_with_buyer(self):
        """Test another farmer cannot start chat with this buyer for this listing."""
        other_farmer = User.objects.create_user(
            username='other_farmer',
            password='Password123!',
            role='farmer'
        )
        self.client.force_login(other_farmer)
        response = self.client.get(reverse('chat:start_chat_with_buyer', args=[self.inquiry.id]))

        # Should redirect with error
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('farmer-detail', args=[self.listing.id]))

        # No conversation should be created with other_farmer
        conv = Conversation.objects.filter(farmer=other_farmer, buyer=self.buyer).first()
        self.assertIsNone(conv)

    def test_superuser_can_start_chat_with_buyer(self):
        """Test superuser can start chat with buyer from any inquiry."""
        superuser = User.objects.create_superuser(
            username='admin',
            password='Password123!',
            role='owner'
        )
        self.client.force_login(superuser)
        response = self.client.get(reverse('chat:start_chat_with_buyer', args=[self.inquiry.id]))

        # Should redirect to chat detail
        self.assertEqual(response.status_code, 302)
        conversation = Conversation.objects.filter(
            farmer=superuser,
            buyer=self.buyer,
            farmer_listing=self.listing
        ).first()
        self.assertIsNotNone(conversation)
        self.assertRedirects(response, reverse('chat:chat_detail', args=[conversation.id]))

    def test_farmer_detail_shows_chat_button_for_inquiries(self):
        """Test farmer detail page includes Chat with Buyer button for inquiries."""
        self.client.force_login(self.farmer)
        response = self.client.get(reverse('farmer-detail', args=[self.listing.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Chat with Buyer')
        self.assertContains(response, reverse('chat:start_chat_with_buyer', args=[self.inquiry.id]))

    def test_buyer_my_applications_shows_chat_button(self):
        """Test buyer's my applications page shows Chat button."""
        self.client.force_login(self.buyer)
        response = self.client.get(reverse('my-applications'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Chat')
        self.assertContains(response, reverse('chat:start_chat', args=[self.listing.id]))

    def test_unauthorized_user_cannot_access_conversation(self):
        """Test that non-participants cannot access the conversation."""
        other_user = User.objects.create_user(
            username='other_user',
            password='Password123!',
            role='buyer'
        )
        self.client.force_login(other_user)

        # Create a conversation
        conv = Conversation.objects.create(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        )

        response = self.client.get(reverse('chat:chat_detail', args=[conv.id]))

        # Should redirect to chat list
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('chat:chat_list'))

    def test_inquiry_without_buyer_user_shows_error(self):
        """Test starting chat with inquiry that has no associated buyer user."""
        from farmer.models import Buyer as Inquiry

        # Create inquiry without a buyer user
        orphan_inquiry = Inquiry.objects.create(
            Farmer=self.listing,
            Buyer=None,
            name='Anonymous Buyer',
            crop_type=self.crop,
            quantity=5,
            budget=10000,
        )

        self.client.force_login(self.farmer)
        response = self.client.get(reverse('chat:start_chat_with_buyer', args=[orphan_inquiry.id]))

        # Should redirect with error
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('farmer-detail', args=[self.listing.id]))

        # No conversation should be created
        conv = Conversation.objects.filter(farmer=self.farmer, buyer=None).first()
        self.assertIsNone(conv)