from django.contrib import admin
from .models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    """
    This is optional but useful — it lets you see and manually edit Job rows in Django's built-in admin interface at http://localhost:8000/admin/.
    """
    list_display = ['id', 'status', 'progress', 'target_column', 'created_at']
    list_filter = ['status']
    readonly_fields = ['id', 'created_at', 'updated_at']