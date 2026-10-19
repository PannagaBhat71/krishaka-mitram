"""
Management command to purge expired moderation data based on VIOLATION_AUTO_PURGE_DAYS setting.
This command permanently deletes sensitive content from resolved incidents and violations
that have passed their purge_scheduled_at date.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from moderation.models import ModerationIncident, ModerationViolation


class Command(BaseCommand):
    help = 'Purge expired moderation data based on VIOLATION_AUTO_PURGE_DAYS setting'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be purged without actually purging',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help='Override VIOLATION_AUTO_PURGE_DAYS setting (default: 30)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Purge all sensitive data regardless of purge_scheduled_at',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        override_days = options['days']

        if override_days is not None:
            purge_days = override_days
        else:
            purge_days = getattr(settings, 'VIOLATION_AUTO_PURGE_DAYS', 30)

        cutoff_date = timezone.now() - timezone.timedelta(days=purge_days)

        self.stdout.write(
            self.style.NOTICE(
                f'Purging moderation data older than {purge_days} days '
                f'(cutoff: {cutoff_date.isoformat()})'
            )
        )

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No data will be modified'))

        # Purge resolved incidents past their purge_scheduled_at
        incidents_query = ModerationIncident.objects.filter(
            status='RESOLVED',
            sensitive_data_purged=False
        )

        if not force:
            incidents_query = incidents_query.filter(
                purge_scheduled_at__lte=timezone.now()
            )

        incidents_to_purge = incidents_query.all()
        incidents_count = incidents_to_purge.count()

        self.stdout.write(f'Found {incidents_count} incidents to purge')

        if incidents_count > 0 and not dry_run:
            purged_incidents = 0
            purged_violations = 0

            for incident in incidents_to_purge:
                # Use the model's purge method which handles cascading
                incident.purge_sensitive_data(purged_by=None)  # System purge
                purged_incidents += 1
                purged_violations += incident.violations.filter(sensitive_data_purged=False).count()

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully purged {purged_incidents} incidents and '
                    f'{purged_violations} violations'
                )
            )
        elif incidents_count > 0 and dry_run:
            # Show what would be purged
            for incident in incidents_to_purge[:10]:
                self.stdout.write(
                    f'  - Incident #{incident.id} (conversation: {incident.conversation_id}, '
                    f'resolved: {incident.resolved_at}, scheduled: {incident.purge_scheduled_at})'
                    f' blocked_content: {incident.blocked_content[:100]}'
                )
            if incidents_count > 10:
                self.stdout.write(f'  ... and {incidents_count - 10} more')

        # Also handle orphaned violations (not linked to incidents) for backward compatibility
        violations_query = ModerationViolation.objects.filter(
            status='RESOLVED',
            sensitive_data_purged=False,
            incident__isnull=True
        )

        if not force:
            violations_query = violations_query.filter(
                purge_scheduled_at__lte=timezone.now()
            )

        violations_to_purge = violations_query.all()
        violations_count = violations_to_purge.count()

        self.stdout.write(f'Found {violations_count} orphaned violations to purge')

        if violations_count > 0 and not dry_run:
            purged = 0
            for violation in violations_to_purge:
                violation.purge_sensitive_data(purged_by=None)
                purged += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully purged {purged} orphaned violations'
                )
            )
        elif violations_count > 0 and dry_run:
            for violation in violations_to_purge[:10]:
                self.stdout.write(
                    f'  - Violation #{violation.id} (rule: {violation.rule.name}, '
                    f'resolved: {violation.resolved_at}, scheduled: {violation.purge_scheduled_at})'
                )
            if violations_count > 10:
                self.stdout.write(f'  ... and {violations_count - 10} more')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN COMPLETE - No data was modified'))
        else:
            self.stdout.write(self.style.SUCCESS('Purge operation completed'))