from django.urls import path
from .views import JobCreateView, FileColumnsView, JobStatusView, JobCancelView

urlpatterns = [
    path('jobs/', JobCreateView.as_view(), name='job-create'),
    path('jobs/columns/', FileColumnsView.as_view(), name='job-columns'),
    path('jobs/<uuid:job_id>/status/', JobStatusView.as_view(), name='job-status'),
    path('jobs/<uuid:job_id>/cancel/', JobCancelView.as_view(), name='job-cancel'),
]