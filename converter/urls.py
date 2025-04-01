from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_page, name='login'),
    path('uploads/', views.uploads, name='uploads'),
    path('convert/<int:resume_id>/', views.convert, name='convert'),
    path('converted/<int:resume_id>/', views.converted, name='converted'),
    path('logout/', views.logout_view, name='logout'),
]