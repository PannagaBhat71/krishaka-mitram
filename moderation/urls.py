from django.urls import path
from . import views

app_name = 'moderation'

urlpatterns = [
    path('login/', views.moderation_login_view, name='moderation_login'),
    path('logout/', views.moderation_logout_view, name='moderation_logout'),
    path('', views.moderation_dashboard_view, name='moderation_dashboard'),
    path('incident/<int:incident_id>/', views.incident_detail_view, name='incident_detail'),
    path('incident/<int:incident_id>/action/', views.incident_action_view, name='incident_action'),
    path('rules/', views.filter_rules_view, name='filter_rules'),
    path('restrictions/', views.user_restrictions_view, name='user_restrictions'),
    path('restriction/<int:restriction_id>/lift/', views.lift_restriction_view, name='lift_restriction'),
    path('api/unread-count/', views.api_unread_count, name='api_unread_count'),
    path('api/notification-count/', views.api_notification_count, name='api_notification_count'),
]