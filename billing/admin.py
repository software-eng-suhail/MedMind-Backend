from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from unfold.admin import ModelAdmin

from .models import CreditTransaction, CreditBundle


@admin.register(CreditTransaction)
class CreditTransactionAdmin(ModelAdmin):
    list_display = (
        "id",
        "doctor_link",
        "bundle",
        "credits_added",
        "amount_usd",
        "status_badge",
        "provider",
        "provider_ref",
        "idempotency_key",
        "created_at",
    )
    search_fields = (
        "doctor__username",
        "doctor__email",
        "provider_ref",
        "idempotency_key",
    )
    list_filter = (
        "status",
        "provider",
        "bundle",
        "created_at",
    )
    readonly_fields = (
        "doctor",
        "bundle",
        "credits_added",
        "amount_usd",
        "status",
        "provider",
        "provider_ref",
        "idempotency_key",
        "metadata",
        "created_at",
    )
    actions = None
    list_per_page = 25

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def doctor_link(self, obj):
        try:
            url = reverse("admin:user_doctoruser_change", args=[obj.doctor.pk])
            return format_html(
                '<a href="{}" class="text-primary-600 dark:text-primary-500">{}</a>',
                url,
                obj.doctor.username,
            )
        except Exception:
            return obj.doctor.username

    doctor_link.short_description = "Doctor"

    def status_badge(self, obj):
        color = {
            obj.Status.PENDING: "bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-400",
            obj.Status.SUCCESS: "bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400",
            obj.Status.FAILED: "bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400",
        }.get(obj.status, "bg-base-100 text-base-700 dark:bg-base-500/20 dark:text-base-200")
        return format_html(
            '<span class="inline-block font-semibold h-6 leading-6 px-2 rounded-default text-[11px] uppercase whitespace-nowrap {}">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"
