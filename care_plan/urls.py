from django.urls import path
from . import views

urlpatterns = [
    path('', views.form_view, name='form'),
    path('submit/', views.submit_view, name='submit'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('orders/<int:order_id>/download/', views.download_care_plan, name='download'),
]
