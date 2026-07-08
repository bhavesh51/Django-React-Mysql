from django.contrib import admin
from restapi.models import Cards, Transaction


@admin.register(Cards)
class CardsAdmin(admin.ModelAdmin):
    list_display = ('id', 'cardholder_name', 'brand', 'last_four', 'expiration_month', 'expiration_year', 'created_at')
    list_filter = ('brand',)
    search_fields = ('cardholder_name', 'last_four')
    readonly_fields = ('id', 'last_four', 'brand', 'created_at')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'transaction_type', 'amount', 'currency', 'status', 'authorization_code', 'created_at')
    list_filter = ('status', 'transaction_type', 'currency')
    search_fields = ('authorization_code', 'merchant_reference', 'description')
    readonly_fields = ('id', 'authorization_code', 'created_at', 'updated_at')
    raw_id_fields = ('card', 'parent_transaction')
