from django.urls import path
from . import views

urlpatterns = [
    path('', views.FarmerListView.as_view(), name='home'),
    path('farmers/', views.FarmerListView.as_view(), name='farmer-list'),
    path('farmer/<int:pk>/', views.FarmerDetailView.as_view(), name='farmer-detail'),
    path('Farmer/<int:pk>/', views.FarmerDetailView.as_view(), name='Farmer-detail'),
    path('farmer/add/', views.FarmerCreateView.as_view(), name='farmer-create'),
    path('farmer/<int:pk>/update/', views.FarmerUpdateView.as_view(), name='farmer-update'),
    path('farmer/<int:pk>/delete/', views.FarmerDeleteView.as_view(), name='farmer-delete'),
    path('my-listings/', views.myFarmerListView.as_view(), name='my-farmers'),
    path('farmer/<int:pk>/apply/', views.apply_to_job, name='apply-job'),
    path('farmer/<int:pk>/inquire/', views.apply_to_job, name='farmer-inquire'),
    path('my-inquiries/', views.MyApplicationListView.as_view(), name='my-applications'),
]
