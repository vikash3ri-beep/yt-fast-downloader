"""
URL configuration for yt_downloader project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
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
from django.contrib import admin
from django.urls import path, re_path, include
from downloader.views import robots_txt_view, sitemap_xml_view, google_verification_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('robots.txt', robots_txt_view, name='robots_txt'),
    path('sitemap.xml', sitemap_xml_view, name='sitemap_xml'),
    re_path(r'^(?P<filename>google[a-zA-Z0-9_\-]+\.html)$', google_verification_view, name='google_verification'),
    path('', include('downloader.urls', namespace='downloader')),
]


