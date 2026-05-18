from django.urls import path
from . import views

urlpatterns = [
    path('', views.form_view, name='form'),
    path('submit/', views.submit_view, name='submit'),
    path('care-plans/<int:care_plan_id>/', views.care_plan_detail, name='care_plan_detail'),
    path('care-plans/<int:care_plan_id>/download/', views.download_care_plan, name='download'),
    path('care-plans/', views.get_care_plans_by_mrn, name='get_care_plans_by_mrn'),
    path('care-plans/<int:care_plan_id>/status/', views.care_plan_status, name='care_plan_status'),
    path('care-plans/<int:care_plan_id>/stream/', views.care_plan_sse, name='care_plan_sse'),
]
