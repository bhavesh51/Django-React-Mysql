import uuid
import random
import string
from decimal import Decimal

from django.http import JsonResponse
from rest_framework.decorators import api_view
from rest_framework import status
from rest_framework.parsers import JSONParser

from restapi.models import Cards, Transaction
from restapi.serializers import (
    CardCreateSerializer,
    CardSerializer,
    TransactionSerializer,
    PaymentRequestSerializer,
    RefundRequestSerializer,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_auth_code():
    """Generate a random 12-character alphanumeric authorisation code."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))


def _simulate_authorization(card_number_digits, amount):
    """
    Simulate the card-network authorisation decision.

    Rules (POC test cards — mirrors Stripe / Braintree test card behaviour):
      - ends in 0000  → always declined (insufficient funds)
      - ends in 9999  → always declined (card declined)
      - amount > 9000 → declined (limit exceeded)
      - otherwise     → approved
    Returns (approved: bool, reason: str)
    """
    last4 = card_number_digits[-4:]
    if last4 == '0000':
        return False, 'Insufficient funds'
    if last4 == '9999':
        return False, 'Card declined by issuer'
    if Decimal(str(amount)) > Decimal('9000.00'):
        return False, 'Transaction limit exceeded'
    return True, ''


# ---------------------------------------------------------------------------
# Card endpoints
# ---------------------------------------------------------------------------

@api_view(['GET', 'POST'])
def card_list(request):
    """
    GET  /api/cards/  — list all tokenised cards (masked).
    POST /api/cards/  — tokenise a new card.
    """
    if request.method == 'GET':
        cards = Cards.objects.all()
        serializer = CardSerializer(cards, many=True)
        return JsonResponse(serializer.data, safe=False, status=status.HTTP_200_OK)

    # POST — tokenise card
    data = JSONParser().parse(request)
    serializer = CardCreateSerializer(data=data)
    if serializer.is_valid():
        card = serializer.save()
        return JsonResponse(
            CardSerializer(card).data,
            status=status.HTTP_201_CREATED,
        )
    return JsonResponse(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'DELETE'])
def card_detail(request, card_id):
    """
    GET    /api/cards/<id>/  — retrieve a single card.
    DELETE /api/cards/<id>/  — delete a card (only if no transactions).
    """
    try:
        card = Cards.objects.get(pk=card_id)
    except Cards.DoesNotExist:
        return JsonResponse({'error': 'Card not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return JsonResponse(CardSerializer(card).data, status=status.HTTP_200_OK)

    # DELETE
    if card.transactions.exists():
        return JsonResponse(
            {'error': 'Cannot delete a card that has associated transactions.'},
            status=status.HTTP_409_CONFLICT,
        )
    card.delete()
    return JsonResponse({}, status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Transaction endpoints
# ---------------------------------------------------------------------------

@api_view(['GET'])
def transaction_list(request):
    """
    GET /api/transactions/  — list all transactions.
    Supports optional query params: status, transaction_type, card_id.
    """
    qs = Transaction.objects.select_related('card').all()

    txn_status = request.GET.get('status')
    txn_type = request.GET.get('transaction_type')
    card_id = request.GET.get('card_id')

    if txn_status:
        qs = qs.filter(status=txn_status)
    if txn_type:
        qs = qs.filter(transaction_type=txn_type)
    if card_id:
        qs = qs.filter(card_id=card_id)

    serializer = TransactionSerializer(qs, many=True)
    return JsonResponse(serializer.data, safe=False, status=status.HTTP_200_OK)


@api_view(['GET'])
def transaction_detail(request, txn_id):
    """GET /api/transactions/<id>/  — retrieve a single transaction."""
    try:
        txn = Transaction.objects.select_related('card').get(pk=txn_id)
    except Transaction.DoesNotExist:
        return JsonResponse({'error': 'Transaction not found.'}, status=status.HTTP_404_NOT_FOUND)
    return JsonResponse(TransactionSerializer(txn).data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Payment processing endpoints
# ---------------------------------------------------------------------------

@api_view(['POST'])
def charge(request):
    """
    POST /api/payments/charge/

    Accepts card details + payment details, tokenises the card on the fly,
    runs a simulated authorisation, and records the transaction.

    Request body:
    {
        "cardholder_name": "Jane Doe",
        "card_number": "4111111111111111",
        "expiration_month": 12,
        "expiration_year": 2026,
        "cvv": "123",
        "amount": "99.99",
        "currency": "USD",
        "description": "Order #1234",
        "merchant_reference": "ORD-1234"
    }
    """
    data = JSONParser().parse(request)
    serializer = PaymentRequestSerializer(data=data)
    if not serializer.is_valid():
        return JsonResponse(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    vd = serializer.validated_data
    raw_number = vd['card_number']

    # Tokenise card (or retrieve existing token if same last-4 + expiry match)
    card = Cards.objects.create(
        cardholder_name=vd['cardholder_name'],
        number=raw_number,
        expiration_month=vd['expiration_month'],
        expiration_year=vd['expiration_year'],
        cvv=vd['cvv'],
    )

    # Simulate network authorisation
    approved, reason = _simulate_authorization(raw_number, vd['amount'])

    txn_status = 'approved' if approved else 'declined'
    auth_code = _generate_auth_code() if approved else ''

    txn = Transaction.objects.create(
        amount=vd['amount'],
        currency=vd.get('currency', 'USD'),
        transaction_type='charge',
        card=card,
        status=txn_status,
        authorization_code=auth_code,
        description=vd.get('description', ''),
        merchant_reference=vd.get('merchant_reference', ''),
        failure_reason=reason,
    )

    http_status = status.HTTP_201_CREATED if approved else status.HTTP_402_PAYMENT_REQUIRED
    return JsonResponse(TransactionSerializer(txn).data, status=http_status)


@api_view(['POST'])
def refund(request, txn_id):
    """
    POST /api/payments/<id>/refund/

    Issues a full or partial refund against an approved charge transaction.

    Request body (all optional):
    {
        "amount": "50.00",           // omit for full refund
        "reason": "Customer return"
    }
    """
    try:
        original = Transaction.objects.select_related('card').get(pk=txn_id)
    except Transaction.DoesNotExist:
        return JsonResponse({'error': 'Transaction not found.'}, status=status.HTTP_404_NOT_FOUND)

    if original.status != 'approved':
        return JsonResponse(
            {'error': f'Cannot refund a transaction with status "{original.status}".'},
            status=status.HTTP_409_CONFLICT,
        )
    if original.transaction_type not in ('charge', 'capture'):
        return JsonResponse(
            {'error': 'Only charge or capture transactions can be refunded.'},
            status=status.HTTP_409_CONFLICT,
        )

    data = JSONParser().parse(request)
    serializer = RefundRequestSerializer(data=data)
    if not serializer.is_valid():
        return JsonResponse(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    vd = serializer.validated_data
    refund_amount = vd.get('amount') or original.amount

    # Verify refund does not exceed original
    already_refunded = sum(
        t.amount for t in original.child_transactions.filter(
            transaction_type='refund', status='approved'
        )
    )
    available = original.amount - already_refunded
    if Decimal(str(refund_amount)) > available:
        return JsonResponse(
            {'error': f'Refund amount exceeds available balance of {available}.'},
            status=status.HTTP_409_CONFLICT,
        )

    refund_txn = Transaction.objects.create(
        amount=refund_amount,
        currency=original.currency,
        transaction_type='refund',
        card=original.card,
        status='approved',
        authorization_code=_generate_auth_code(),
        description=vd.get('reason', 'Refund'),
        merchant_reference=original.merchant_reference,
        parent_transaction=original,
    )

    # If fully refunded mark original as refunded
    total_refunded = already_refunded + Decimal(str(refund_amount))
    if total_refunded >= original.amount:
        original.status = 'refunded'
        original.save(update_fields=['status', 'updated_at'])

    return JsonResponse(TransactionSerializer(refund_txn).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def void_transaction(request, txn_id):
    """
    POST /api/payments/<id>/void/

    Voids a pending or approved charge before settlement.
    """
    try:
        txn = Transaction.objects.select_related('card').get(pk=txn_id)
    except Transaction.DoesNotExist:
        return JsonResponse({'error': 'Transaction not found.'}, status=status.HTTP_404_NOT_FOUND)

    if txn.status not in ('pending', 'approved'):
        return JsonResponse(
            {'error': f'Cannot void a transaction with status "{txn.status}".'},
            status=status.HTTP_409_CONFLICT,
        )

    txn.status = 'voided'
    txn.save(update_fields=['status', 'updated_at'])
    return JsonResponse(TransactionSerializer(txn).data, status=status.HTTP_200_OK)


@api_view(['GET'])
def payment_status(request, txn_id):
    """
    GET /api/payments/<id>/status/

    Returns only the status fields for a transaction (lightweight polling endpoint).
    """
    try:
        txn = Transaction.objects.select_related('card').get(pk=txn_id)
    except Transaction.DoesNotExist:
        return JsonResponse({'error': 'Transaction not found.'}, status=status.HTTP_404_NOT_FOUND)

    return JsonResponse({
        'id': str(txn.id),
        'status': txn.status,
        'authorization_code': txn.authorization_code,
        'failure_reason': txn.failure_reason,
        'amount': str(txn.amount),
        'currency': txn.currency,
        'transaction_type': txn.transaction_type,
        'updated_at': txn.updated_at.isoformat(),
    }, status=status.HTTP_200_OK)
