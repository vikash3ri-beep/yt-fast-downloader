from django.urls import path
from . import views

app_name = 'downloader'

urlpatterns = [
    path('', views.index_view, name='index'),
    path('results/', views.results_view, name='results'),
    path('api/extract/', views.api_extract_info, name='api_extract'),
    path('api/prepare/', views.api_prepare_download, name='api_prepare'),
    path('api/progress/<str:job_id>/', views.api_download_progress, name='api_progress'),
    path('download-ready/<str:job_id>/', views.download_ready_view, name='download_ready'),
    path('download/', views.download_view, name='download'),
]
