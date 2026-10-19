from django.contrib import admin
from .models import Conversation, Message


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'farmer', 'buyer', 'farmer_listing', 'is_active', 'created_at', 'updated_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['farmer__username', 'buyer__username', 'farmer_listing__crop_name__name']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'sender', 'content_preview', 'is_filtered', 'filter_types', 'created_at', 'is_deleted']
    list_filter = ['is_filtered', 'is_deleted', 'created_at']
    search_fields = ['content', 'sender__username', 'conversation__id']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'

    def content_preview(self, obj):
        return obj.content[:80] + ('...' if len(obj.content) > 80 else '')
    content_preview.short_description = 'Content'