from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'created_at', 'actor', 'action', 'object_type', 'object_id', 'ip_address']
    list_filter = ['action', 'object_type']
    search_fields = ['actor__username', 'object_type', 'object_id', 'details']
    readonly_fields = ['created_at', 'actor', 'action', 'object_type', 'object_id', 'details', 'ip_address', 'user_agent']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False  # Audit logs should only be created programmatically

    def has_change_permission(self, request, obj=None):
        return False  # Audit logs are append-only

    def has_delete_permission(self, request, obj=None):
        return False  # Audit logs are immutable