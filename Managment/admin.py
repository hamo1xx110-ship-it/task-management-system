from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Department, Task, User

admin.site.register(Department)
admin.site.register(Task)



@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "role", "department", "is_active")
    list_filter = ("role", "department")
    fieldsets = UserAdmin.fieldsets + (
        ("Company", {"fields": ("role", "department")}),
    )
