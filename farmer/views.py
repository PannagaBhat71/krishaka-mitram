from django.shortcuts import render, redirect, get_object_or_404
from django.db import models
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib import messages
from .models import Crop, Farmer, Buyer
from .forms import Farmerform

# Create your views here.


class FarmerListView(ListView):
    model = Farmer
    template_name = 'farmer/farmer_list.html'
    context_object_name = 'farmers'

    def get_queryset(self):
        queryset = Farmer.objects.select_related('crop_name', 'crop_type', 'posted_by').order_by('-date_posted', '-id')
        q = self.request.GET.get('q')
        crop_id = self.request.GET.get('crop')
        location = self.request.GET.get('location')
        if q:
            queryset = queryset.filter(
                models.Q(name__icontains=q) |
                models.Q(location__icontains=q) |
                models.Q(crop_name__name__icontains=q) |
                models.Q(crop_type__name__icontains=q)
            )
        if crop_id:
            queryset = queryset.filter(crop_name_id=crop_id)
        if location:
            queryset = queryset.filter(location__icontains=location)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['crops'] = Crop.objects.all()
        context['selected_crop'] = self.request.GET.get('crop', '')
        context['search_query'] = self.request.GET.get('q', '')
        context['selected_location'] = self.request.GET.get('location', '')
        return context



class FarmerDetailView(DetailView):
    model = Farmer
    template_name = 'farmer/farmer_detail.html'
    context_object_name = 'farmer'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            has_applied = Buyer.objects.filter(
                Farmer=self.object, Buyer=self.request.user
            ).exists()
            context['already_applied'] = has_applied
            context['already applied'] = has_applied
            # If current user is the owner, provide incoming inquiries
            if self.request.user == self.object.posted_by or self.request.user.is_superuser:
                context['inquiries'] = self.object.inquiries.select_related('Buyer').order_by('-date_applied')
        else:
            context['already_applied'] = False
            context['already applied'] = False
        return context



class FarmerCreateView(LoginRequiredMixin, CreateView):
    model = Farmer
    form_class = Farmerform
    template_name = 'farmer/farmer_form.html'

    def form_valid(self, form):
        form.instance.posted_by = self.request.user
        messages.success(self.request, "Farmer produce listing created successfully!")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('farmer-detail', kwargs={'pk': self.object.pk})



class FarmerUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Farmer
    form_class = Farmerform
    template_name = 'farmer/farmer_form.html'

    def form_valid(self, form):
        messages.success(self.request, "Farmer produce listing updated successfully!")
        return super().form_valid(form)

    def test_func(self):
        farmer_obj = self.get_object()
        if self.request.user.is_superuser:
            return True
        return self.request.user == farmer_obj.posted_by

    def get_success_url(self):
        return reverse_lazy('farmer-detail', kwargs={'pk': self.object.pk})



class FarmerDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Farmer
    template_name = 'farmer/farmer_confirm_delete.html'
    success_url = reverse_lazy('my-farmers')

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Farmer produce listing deleted successfully!")
        return super().delete(request, *args, **kwargs)

    def test_func(self):
        farmer_obj = self.get_object()
        if self.request.user.is_superuser:
            return True
        return self.request.user == farmer_obj.posted_by



class myFarmerListView(LoginRequiredMixin, ListView):
    model = Farmer
    template_name = 'farmer/my_farmers.html'
    context_object_name = 'farmers'

    def get_queryset(self):
        return Farmer.objects.filter(posted_by=self.request.user).select_related('crop_name', 'crop_type').order_by('-date_posted')



@login_required
def apply_to_job(request, pk):
    farm_obj = get_object_or_404(Farmer, pk=pk)

    # Prevent owner from applying to their own listing
    if farm_obj.posted_by == request.user:
        messages.warning(request, "You cannot send a buyer inquiry for your own produce listing.")
        return redirect('farmer-detail', pk=pk)

    # Check or create application/inquiry
    application, created = Buyer.objects.get_or_create(
        Farmer=farm_obj,
        Buyer=request.user,
        defaults={
            'name': request.user.get_full_name() or request.user.username,
            'crop_type': farm_obj.crop_name,
            'quantity': farm_obj.quantity,
            'budget': farm_obj.price,
        }
    )

    if created:
        messages.success(request, f"Inquiry sent! You expressed interest in {farm_obj.name}'s {farm_obj.crop_name}.")
    else:
        messages.info(request, "You have already sent an inquiry for this produce listing.")

    return redirect('farmer-detail', pk=pk)



class MyApplicationListView(LoginRequiredMixin, ListView):
    model = Buyer
    template_name = 'farmer/my_applications.html'
    context_object_name = 'applications'

    def get_queryset(self):
        return Buyer.objects.filter(Buyer=self.request.user).select_related('Farmer', 'Farmer__crop_name', 'Farmer__crop_type').order_by('-date_applied')