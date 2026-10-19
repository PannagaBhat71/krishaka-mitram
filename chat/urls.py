from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('login/', views.chat_login_view, name='chat_login'),
    path('logout/', views.chat_logout_view, name='chat_logout'),
    path('', views.chat_list_view, name='chat_list'),
    path('start/<int:farmer_id>/', views.start_chat_view, name='start_chat'),
    path('start-with-buyer/<int:inquiry_id>/', views.start_chat_with_buyer_view, name='start_chat_with_buyer'),
    path('conversation/<int:conversation_id>/', views.chat_detail_view, name='chat_detail'),
    path('conversation/<int:conversation_id>/send/', views.send_message_view, name='send_message'),
    path('conversation/<int:conversation_id>/close/', views.close_conversation_view, name='close_conversation'),
]