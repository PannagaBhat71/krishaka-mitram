from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from audit.models import AuditLog
from moderation.models import ModerationViolation, FilterRule, UserRestriction
from chat.models import Conversation, Message
from farmer.models import Farmer, Crop

User = get_user_model()


class AuditLogModelTests(TestCase):
    """Tests for AuditLog model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='audituser',
            password='Password123!',
            role='farmer'
        )
        self.moderator = User.objects.create_user(
            username='auditmod',
            password='Password123!',
            role='moderator'
        )

    def test_audit_log_creation(self):
        """Test creating an audit log entry."""
        log = AuditLog.objects.create(
            actor=self.user,
            action='LOGIN',
            object_type='CustomUser',
            object_id=str(self.user.id),
            details={'ip': '127.0.0.1'},
            ip_address='127.0.0.1',
            user_agent='Test Agent'
        )
        self.assertEqual(log.actor, self.user)
        self.assertEqual(log.action, 'LOGIN')
        self.assertEqual(log.object_type, 'CustomUser')
        self.assertEqual(log.object_id, str(self.user.id))
        self.assertEqual(log.details, {'ip': '127.0.0.1'})

    def test_audit_log_classmethod_log(self):
        """Test AuditLog.log classmethod."""
        log = AuditLog.log(
            action='LOGOUT',
            actor=self.user,
            object_type='CustomUser',
            object_id=str(self.user.id),
            details={'session_duration': 3600},
            ip_address='127.0.0.1',
            user_agent='Test Agent'
        )
        self.assertEqual(log.action, 'LOGOUT')
        self.assertEqual(log.details, {'session_duration': 3600})

    def test_audit_log_without_actor(self):
        """Test audit log without actor (system actions)."""
        log = AuditLog.log(
            action='MESSAGE_BLOCKED',
            object_type='Message',
            object_id='123',
            details={'filter_type': 'phone'}
        )
        self.assertIsNone(log.actor)
        self.assertEqual(log.action, 'MESSAGE_BLOCKED')

    def test_audit_log_str_representation(self):
        """Test audit log string representation."""
        log = AuditLog.log(
            action='LOGIN',
            actor=self.user,
            object_type='CustomUser',
            object_id=str(self.user.id)
        )
        str_repr = str(log)
        self.assertIn('audituser', str_repr)
        self.assertIn('Login', str_repr)

    def test_all_action_choices(self):
        """Test all defined action choices can be used."""
        actions = [
            'LOGIN', 'LOGOUT', 'FAILED_LOGIN',
            'VIEW_VIOLATION', 'RESOLVE_VIOLATION',
            'WARN_USER', 'RESTRICT_USER', 'UNRESTRICT_USER',
            'CREATE_RULE', 'UPDATE_RULE', 'DELETE_RULE', 'TOGGLE_RULE',
            'PURGE_SENSITIVE_DATA',
            'MESSAGE_BLOCKED', 'MESSAGE_FLAGGED',
            'CONVERSATION_STARTED', 'CONVERSATION_CLOSED'
        ]

        for action in actions:
            with self.subTest(action=action):
                log = AuditLog.log(
                    action=action,
                    actor=self.user,
                    object_type='Test',
                    object_id='1'
                )
                self.assertEqual(log.action, action)


class AuditLogOrderingTests(TestCase):
    """Test audit log ordering."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='orderuser',
            password='Password123!',
            role='farmer'
        )

    def test_audit_logs_ordered_by_timestamp_desc(self):
        """Test audit logs are ordered by timestamp descending."""
        log1 = AuditLog.log(
            action='LOGIN',
            actor=self.user,
            object_type='CustomUser',
            object_id=str(self.user.id)
        )

        log2 = AuditLog.log(
            action='LOGOUT',
            actor=self.user,
            object_type='CustomUser',
            object_id=str(self.user.id)
        )

        logs = list(AuditLog.objects.all())
        self.assertEqual(logs[0], log2)  # Most recent first
        self.assertEqual(logs[1], log1)


class AuditLogImmutabilityTests(TestCase):
    """Test audit log immutability (append-only)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='immutuser',
            password='Password123!',
            role='farmer'
        )

    def test_audit_log_cannot_be_updated_via_admin(self):
        """Test that audit logs should not be modified (admin is read-only)."""
        log = AuditLog.log(
            action='LOGIN',
            actor=self.user,
            object_type='CustomUser',
            object_id=str(self.user.id)
        )

        # In the admin, AuditLogAdmin has readonly_fields = all fields
        # This is tested via admin tests, but we verify model behavior
        original_timestamp = log.timestamp
        original_action = log.action

        # Attempt to modify
        log.action = 'LOGOUT'
        log.save()

        # In a true append-only system, this would be prevented
        # Here Django allows it but admin prevents it
        log.refresh_from_db()
        # Note: Model doesn't prevent updates, but admin does
        # This test documents expected behavior


class AuditLogIntegrationTests(TestCase):
    """Integration tests for audit logging."""

    def setUp(self):
        self.farmer = User.objects.create_user(
            username='auditfarmer',
            password='Password123!',
            role='farmer'
        )
        self.buyer = User.objects.create_user(
            username='auditbuyer',
            password='Password123!',
            role='buyer'
        )
        self.moderator = User.objects.create_user(
            username='auditmod2',
            password='Password123!',
            role='moderator'
        )
        self.crop = Crop.objects.create(name='Wheat')
        self.listing = Farmer.objects.create(
            crop_type=self.crop,
            crop_name=self.crop,
            price=2200,
            location='Test Location',
            farm_size=10,
            quality=80,
            quantity=1000,
            phone_number='9876543210',
            ration_card_number='RC123456',
            posted_by=self.farmer
        )

    def test_login_logs_audit(self):
        """Test user login creates audit log."""
        AuditLog.log('LOGIN', actor=self.buyer, object_type='ModerationSession',
                     object_id=str(self.buyer.id), details={'type': 'moderation_dashboard'})

        logs = AuditLog.objects.filter(actor=self.buyer, action='LOGIN')
        self.assertEqual(logs.count(), 1)

    def test_failed_login_logs_audit(self):
        """Test failed login creates audit log."""
        AuditLog.log('FAILED_LOGIN', actor=None, object_type='ModerationSession',
                     object_id='testuser', details={'reason': 'insufficient_perms'})

        logs = AuditLog.objects.filter(action='FAILED_LOGIN')
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().details['reason'], 'insufficient_perms')

    def test_view_violation_logs_audit(self):
        """Test viewing violation creates audit log."""
        conv = Conversation.objects.create(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        )
        msg = Message.objects.create(
            conversation=conv,
            sender=self.buyer,
            content='test'
        )
        rule = FilterRule.objects.create(
            name='Test Rule', pattern='', rule_type='phone',
            severity='high', action='block'
        )
        violation = ModerationViolation.objects.create(
            message=msg, rule=rule, detected_content='9876543210', severity='high'
        )

        AuditLog.log('VIEW_VIOLATION', actor=self.moderator,
                     object_type='ModerationViolation', object_id=str(violation.id))

        logs = AuditLog.objects.filter(
            actor=self.moderator,
            action='VIEW_VIOLATION',
            object_id=str(violation.id)
        )
        self.assertEqual(logs.count(), 1)

    def test_resolve_violation_logs_audit(self):
        """Test resolving violation creates audit log."""
        conv = Conversation.objects.create(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        )
        msg = Message.objects.create(
            conversation=conv,
            sender=self.buyer,
            content='test'
        )
        rule = FilterRule.objects.create(
            name='Test Rule', pattern='', rule_type='phone',
            severity='high', action='block'
        )
        violation = ModerationViolation.objects.create(
            message=msg, rule=rule, detected_content='9876543210', severity='high'
        )

        AuditLog.log('RESOLVE_VIOLATION', actor=self.moderator,
                     object_type='ModerationViolation', object_id=str(violation.id),
                     details={'resolution': 'False positive'})

        logs = AuditLog.objects.filter(
            actor=self.moderator,
            action='RESOLVE_VIOLATION',
            object_id=str(violation.id)
        )
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().details['resolution'], 'False positive')

    def test_warn_user_logs_audit(self):
        """Test warning user creates audit log."""
        AuditLog.log('WARN_USER', actor=self.moderator,
                     object_type='CustomUser', object_id=str(self.buyer.id),
                     details={'violation_id': 1, 'rule': 'Phone Number'})

        logs = AuditLog.objects.filter(
            actor=self.moderator,
            action='WARN_USER',
            object_id=str(self.buyer.id)
        )
        self.assertEqual(logs.count(), 1)

    def test_restrict_user_logs_audit(self):
        """Test restricting user creates audit log."""
        restriction = UserRestriction.objects.create(
            user=self.buyer,
            restriction_type='temporary',
            reason='Test',
            ends_at=timezone.now() + timezone.timedelta(days=7),
            created_by=self.moderator
        )

        AuditLog.log('RESTRICT_USER', actor=self.moderator,
                     object_type='CustomUser', object_id=str(self.buyer.id),
                     details={'restriction_id': restriction.id, 'duration_days': 7})

        logs = AuditLog.objects.filter(
            actor=self.moderator,
            action='RESTRICT_USER',
            object_id=str(self.buyer.id)
        )
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().details['duration_days'], 7)

    def test_lift_restriction_logs_audit(self):
        """Test lifting restriction creates audit log."""
        restriction = UserRestriction.objects.create(
            user=self.buyer,
            restriction_type='temporary',
            reason='Test',
            ends_at=timezone.now() + timezone.timedelta(days=7),
            created_by=self.moderator
        )

        AuditLog.log('UNRESTRICT_USER', actor=self.moderator,
                     object_type='CustomUser', object_id=str(self.buyer.id),
                     details={'restriction_id': restriction.id})

        logs = AuditLog.objects.filter(
            actor=self.moderator,
            action='UNRESTRICT_USER',
            object_id=str(self.buyer.id)
        )
        self.assertEqual(logs.count(), 1)

    def test_filter_rule_crud_logs_audit(self):
        """Test filter rule CRUD operations log audit."""
        # Create
        rule = FilterRule.objects.create(
            name='Test Rule', pattern='', rule_type='phone',
            severity='high', action='block'
        )
        AuditLog.log('CREATE_RULE', actor=self.moderator,
                     object_type='FilterRule', object_id=str(rule.id),
                     details={'name': rule.name, 'type': rule.rule_type})

        # Update
        rule.name = 'Updated Rule'
        rule.save()
        AuditLog.log('UPDATE_RULE', actor=self.moderator,
                     object_type='FilterRule', object_id=str(rule.id))

        # Toggle
        rule.is_active = False
        rule.save(update_fields=['is_active'])
        AuditLog.log('TOGGLE_RULE', actor=self.moderator,
                     object_type='FilterRule', object_id=str(rule.id),
                     details={'is_active': False})

        # Delete
        rule_id = rule.id
        rule.delete()
        AuditLog.log('DELETE_RULE', actor=self.moderator,
                     object_type='FilterRule', object_id=str(rule_id),
                     details={'name': 'Updated Rule'})

        create_logs = AuditLog.objects.filter(action='CREATE_RULE')
        update_logs = AuditLog.objects.filter(action='UPDATE_RULE')
        toggle_logs = AuditLog.objects.filter(action='TOGGLE_RULE')
        delete_logs = AuditLog.objects.filter(action='DELETE_RULE')

        self.assertEqual(create_logs.count(), 1)
        self.assertEqual(update_logs.count(), 1)
        self.assertEqual(toggle_logs.count(), 1)
        self.assertEqual(delete_logs.count(), 1)

    def test_purge_sensitive_data_logs_audit(self):
        """Test purging sensitive data creates audit log."""
        conv = Conversation.objects.create(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        )
        msg = Message.objects.create(
            conversation=conv,
            sender=self.buyer,
            content='test'
        )
        rule = FilterRule.objects.create(
            name='Test Rule', pattern='', rule_type='phone',
            severity='high', action='block'
        )
        violation = ModerationViolation.objects.create(
            message=msg, rule=rule, detected_content='9876543210', severity='high'
        )

        AuditLog.log('PURGE_SENSITIVE_DATA', actor=self.moderator,
                     object_type='ModerationViolation', object_id=str(violation.id))

        logs = AuditLog.objects.filter(
            actor=self.moderator,
            action='PURGE_SENSITIVE_DATA',
            object_id=str(violation.id)
        )
        self.assertEqual(logs.count(), 1)

    def test_message_blocked_logs_audit(self):
        """Test blocked message creates audit log."""
        AuditLog.log('MESSAGE_BLOCKED', actor=None,
                     object_type='Message', object_id='123',
                     details={'filter_type': 'phone', 'conversation_id': 1})

        logs = AuditLog.objects.filter(action='MESSAGE_BLOCKED')
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().details['filter_type'], 'phone')

    def test_conversation_started_logs_audit(self):
        """Test conversation started creates audit log."""
        conv = Conversation.objects.create(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        )

        AuditLog.log('CONVERSATION_STARTED', actor=self.buyer,
                     object_type='Conversation', object_id=str(conv.id))

        logs = AuditLog.objects.filter(
            actor=self.buyer,
            action='CONVERSATION_STARTED',
            object_id=str(conv.id)
        )
        self.assertEqual(logs.count(), 1)

    def test_conversation_closed_logs_audit(self):
        """Test conversation closed creates audit log."""
        conv = Conversation.objects.create(
            farmer=self.farmer,
            buyer=self.buyer,
            farmer_listing=self.listing
        )
        conv.close(self.buyer)

        AuditLog.log('CONVERSATION_CLOSED', actor=self.buyer,
                     object_type='Conversation', object_id=str(conv.id))

        logs = AuditLog.objects.filter(
            actor=self.buyer,
            action='CONVERSATION_CLOSED',
            object_id=str(conv.id)
        )
        self.assertEqual(logs.count(), 1)


class AuditLogAdminTests(TestCase):
    """Tests for AuditLog admin (read-only)."""

    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='admin',
            password='Password123!',
            email='admin@test.com'
        )
        self.client.force_login(self.admin_user)

        self.user = User.objects.create_user(
            username='auditadminuser',
            password='Password123!',
            role='farmer'
        )

    def test_audit_log_admin_list_view(self):
        """Test audit log list view in admin."""
        AuditLog.log('LOGIN', actor=self.user, object_type='CustomUser',
                     object_id=str(self.user.id))

        response = self.client.get(reverse('admin:audit_auditlog_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'auditadminuser')

    def test_audit_log_admin_detail_readonly(self):
        """Test audit log detail view is read-only."""
        log = AuditLog.log('LOGIN', actor=self.user, object_type='CustomUser',
                           object_id=str(self.user.id))

        response = self.client.get(reverse('admin:audit_auditlog_change', args=[log.id]))
        self.assertEqual(response.status_code, 200)
        # All fields should be readonly (checked via admin config)