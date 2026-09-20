from django.contrib import admin
from .models import *

# Register your models here.
@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'email', 'external_customer_id']

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'code', 'interval', 'amount', 'currency', 'trial_period_days', 'is_active']

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'plan', 'status', 'current_period_start', 'current_period_end', 'trial_end', 'cancel_at_period_end', 'canceled_at', 'external_subscription_id']

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'subscription', 'status', 'amount_due', 'currency', 'period_start', 'period_end', 'paid_at', 'external_invoice_id']

@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ['id', 'external_event_id', 'event_type', 'payload', 'status', 'error_message', 'processed_at']