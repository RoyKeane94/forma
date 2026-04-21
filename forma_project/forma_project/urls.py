"""
URL configuration for forma_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView

_admin_path = getattr(settings, 'DJANGO_ADMIN_PATH', 'admin').strip('/')

urlpatterns = [
    path(
        'admin',
        RedirectView.as_view(url=f'/{_admin_path}/', permanent=False),
        name='admin_slash_redirect',
    ),
]

# If admin lives on a non-default path, keep /admin/ as a redirect for bookmarks.
if _admin_path != 'admin':
    urlpatterns.append(
        path(
            'admin/',
            RedirectView.as_view(url=f'/{_admin_path}/', permanent=False),
        )
    )

urlpatterns += [
    path(f'{_admin_path}/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('', include('pages.urls')),
    path('', TemplateView.as_view(template_name='home.html'), name='home'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler400 = 'pages.views.bad_request'
handler403 = 'pages.views.permission_denied'
handler404 = 'pages.views.page_not_found'
handler500 = 'pages.views.server_error'
