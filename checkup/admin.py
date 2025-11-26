from django.contrib import admin
from .models import Checkup, SkinCancerCheckup

admin.site.register(Checkup)
admin.site.register(SkinCancerCheckup)