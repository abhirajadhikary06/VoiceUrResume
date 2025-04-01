from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.views import LogoutView  # Import LogoutView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('converter.urls')),
    path('oauth/', include('social_django.urls', namespace='social')),
    path('logout/', LogoutView.as_view(), name='logout'),  # Add this line
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
