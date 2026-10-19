from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.notification_list_view, name='notification_list'),
    path('<int:notification_id>/read/', views.mark_notification_read_view, name='mark_read'),
    path('mark-all-read/', views.mark_all_read_view, name='mark_all_read'),
    path('api/count/', views.api_notification_count, name='api_count'),
    path('api/recent/', views.api_recent_notifications, name='api_recent'),
]