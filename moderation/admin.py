from django.contrib import admin
from .models import FilterRule, ModerationViolation, UserRestriction, ModerationIncident


@admin.register(FilterRule)
class FilterRuleAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'rule_type', 'is_active', 'severity', 'action', 'created_at', 'violations_count']
    list_filter = ['rule_type', 'is_active', 'severity', 'action']
    search_fields = ['name', 'pattern', 'description']
    readonly_fields = ['created_at', 'updated_at']
    list_editable = ['is_active']

    def violations_count(self, obj):
        return obj.violations.count()
    violations_count.short_description = 'Violations'


@admin.register(ModerationIncident)
class ModerationIncidentAdmin(admin.ModelAdmin):
    list_display = ['id', 'status', 'conversation', 'submitting_user', 'assigned_moderator', 'created_at', 'violations_count']
    list_filter = ['status', 'assigned_moderator']
    search_fields = ['conversation__id', 'submitting_user__username', 'blocked_content']
    readonly_fields = ['created_at', 'viewed_at', 'resolved_at', 'purged_at', 'purge_scheduled_at']
    raw_id_fields = ['conversation', 'submitting_user', 'message', 'assigned_moderator']
    date_hierarchy = 'created_at'

    def violations_count(self, obj):
        return obj.violations.count()
    violations_count.short_description = 'Violations'


@admin.register(ModerationViolation)
class ModerationViolationAdmin(admin.ModelAdmin):
    list_display = ['id', 'incident', 'rule', 'status', 'severity', 'assigned_moderator', 'created_at', 'resolved_at']
    list_filter = ['status', 'severity', 'rule__rule_type']
    search_fields = ['incident__id', 'rule__name', 'detected_content', 'resolution']
    readonly_fields = ['created_at', 'viewed_at', 'resolved_at', 'purged_at']
    raw_id_fields = ['incident', 'rule', 'assigned_moderator']
    date_hierarchy = 'created_at'


@admin.register(UserRestriction)
class UserRestrictionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'restriction_type', 'is_active', 'starts_at', 'ends_at', 'created_by', 'created_at']
    list_filter = ['restriction_type', 'is_active']
    search_fields = ['user__username', 'reason']
    readonly_fields = ['created_at']
    raw_id_fields = ['user', 'incident', 'violation', 'created_by']
    date_hierarchy = 'created_at'