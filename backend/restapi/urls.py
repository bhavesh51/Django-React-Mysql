from django.urls import path
from restapi import views

urlpatterns = [
    # Card tokenisation
    path('api/cards/', views.card_list, name='card-list'),
    path('api/cards/<uuid:card_id>/', views.card_detail, name='card-detail'),

    # Transaction history
    path('api/transactions/', views.transaction_list, name='transaction-list'),
    path('api/transactions/<uuid:txn_id>/', views.transaction_detail, name='transaction-detail'),

    # Payment processing
    path('api/payments/charge/', views.charge, name='payment-charge'),
    path('api/payments/<uuid:txn_id>/refund/', views.refund, name='payment-refund'),
    path('api/payments/<uuid:txn_id>/void/', views.void_transaction, name='payment-void'),
    path('api/payments/<uuid:txn_id>/status/', views.payment_status, name='payment-status'),
]
