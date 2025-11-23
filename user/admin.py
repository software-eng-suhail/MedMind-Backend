from django.contrib import admin
from .models import User, AdminProfile, DoctorProfile


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
	list_display = ('username', 'email', 'role', 'is_staff', 'is_active')


admin.site.register(AdminProfile)
admin.site.register(DoctorProfile)