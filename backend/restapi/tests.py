"""
Comprehensive test suite for the Payment Gateway POC.

Coverage:
  - Model layer: Cards (branding, masking, Luhn) and Transaction
  - Serializer layer: CardCreateSerializer, PaymentRequestSerializer, RefundRequestSerializer
  - View / API layer: end-to-end HTTP tests against all endpoints
  - Business logic: approved charge, declined charge, full refund, partial refund,
                    void, double-refund guard, refund-on-declined guard

Run with:
    python manage.py test restapi
"""

import json
import uuid
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse

from restapi.models import Cards, Transaction
from restapi.serializers import (
    CardCreateSerializer,
    PaymentRequestSerializer,
    RefundRequestSerializer,
)
from restapi.views import _generate_auth_code, _simulate_authorization


# ---------------------------------------------------------------------------
# Helper: valid Visa test card (Luhn-valid)
# ---------------------------------------------------------------------------
VISA_NUMBER = '4111111111111111'
MASTERCARD_NUMBER = '5500005555555559'
AMEX_NUMBER = '378282246310005'
DECLINE_INSUF = '4111111111110000'  # ends 0000 → insufficient funds
DECLINE_ISSUER = '4111111111119999'  # ends 9999 → declined by issuer
INVALID_LUHN = '4111111111111112'

VALID_CARD_PAYLOAD = {
    'cardholder_name': 'Jane Doe',
    'card_number': VISA_NUMBER,
    'expiration_month': 12,
    'expiration_year': 2030,
    'cvv': '123',
    'amount': '99.99',
    'currency': 'USD',
    'description': 'Test charge',
    'merchant_reference': 'ORD-001',
}


# ===========================================================================
# Model tests
# ===========================================================================

class CardModelTest(TestCase):
    """Tests for Cards.save() logic: masking, brand detection."""

    def _create_card(self, number, name='Test User', month=12, year=2030, cvv='123'):
        return Cards.objects.create(
            cardholder_name=name,
            number=number,
            expiration_month=month,
            expiration_year=year,
            cvv=cvv,
        )

    def test_visa_brand_detected(self):
        card = self._create_card(VISA_NUMBER)
        self.assertEqual(card.brand, 'Visa')

    def test_mastercard_brand_detected(self):
        card = self._create_card(MASTERCARD_NUMBER)
        self.assertEqual(card.brand, 'Mastercard')

    def test_amex_brand_detected(self):
        card = self._create_card(AMEX_NUMBER)
        self.assertEqual(card.brand, 'Amex')

    def test_last_four_stored(self):
        card = self._create_card(VISA_NUMBER)
        self.assertEqual(card.last_four, '1111')

    def test_pan_is_masked_after_save(self):
        card = self._create_card(VISA_NUMBER)
        self.assertIn('****', card.number)
        self.assertNotIn(VISA_NUMBER, card.number)

    def test_cvv_is_cleared_after_save(self):
        card = self._create_card(VISA_NUMBER)
        self.assertEqual(card.cvv, '')

    def test_str_representation(self):
        card = self._create_card(VISA_NUMBER, name='Alice')
        self.assertIn('1111', str(card))
        self.assertIn('Alice', str(card))


class TransactionModelTest(TestCase):
    """Tests for Transaction model fields and __str__."""

    def setUp(self):
        self.card = Cards.objects.create(
            cardholder_name='Bob',
            number=VISA_NUMBER,
            expiration_month=12,
            expiration_year=2030,
            cvv='123',
        )

    def test_create_transaction(self):
        txn = Transaction.objects.create(
            amount=Decimal('50.00'),
            currency='USD',
            transaction_type='charge',
            card=self.card,
            status='approved',
            authorization_code='ABC123',
        )
        self.assertEqual(txn.transaction_type, 'charge')
        self.assertEqual(txn.status, 'approved')
        self.assertEqual(txn.amount, Decimal('50.00'))

    def test_str_representation(self):
        txn = Transaction.objects.create(
            amount=Decimal('10.00'),
            currency='USD',
            transaction_type='charge',
            card=self.card,
            status='approved',
        )
        s = str(txn)
        self.assertIn('CHARGE', s)
        self.assertIn('approved', s)

    def test_parent_transaction_link(self):
        charge = Transaction.objects.create(
            amount=Decimal('100.00'),
            currency='USD',
            transaction_type='charge',
            card=self.card,
            status='approved',
        )
        refund = Transaction.objects.create(
            amount=Decimal('100.00'),
            currency='USD',
            transaction_type='refund',
            card=self.card,
            status='approved',
            parent_transaction=charge,
        )
        self.assertEqual(refund.parent_transaction, charge)
        self.assertIn(refund, charge.child_transactions.all())


# ===========================================================================
# Serializer tests
# ===========================================================================

class CardCreateSerializerTest(TestCase):

    def _payload(self, **overrides):
        p = {
            'cardholder_name': 'Jane Doe',
            'number': VISA_NUMBER,
            'expiration_month': 12,
            'expiration_year': 2030,
            'cvv': '123',
        }
        p.update(overrides)
        return p

    def test_valid_visa_card(self):
        s = CardCreateSerializer(data=self._payload())
        self.assertTrue(s.is_valid(), s.errors)

    def test_luhn_failure(self):
        s = CardCreateSerializer(data=self._payload(number=INVALID_LUHN))
        self.assertFalse(s.is_valid())
        self.assertIn('number', s.errors)

    def test_non_digit_card_number(self):
        s = CardCreateSerializer(data=self._payload(number='4111-XXXX-1111-1111'))
        self.assertFalse(s.is_valid())

    def test_expired_card_rejected(self):
        s = CardCreateSerializer(data=self._payload(expiration_year=2020, expiration_month=1))
        self.assertFalse(s.is_valid())

    def test_invalid_month(self):
        s = CardCreateSerializer(data=self._payload(expiration_month=13))
        self.assertFalse(s.is_valid())

    def test_short_cvv(self):
        s = CardCreateSerializer(data=self._payload(cvv='12'))
        self.assertFalse(s.is_valid())


class PaymentRequestSerializerTest(TestCase):

    def _payload(self, **overrides):
        p = dict(VALID_CARD_PAYLOAD)
        p.update(overrides)
        return p

    def test_valid_payload(self):
        s = PaymentRequestSerializer(data=self._payload())
        self.assertTrue(s.is_valid(), s.errors)

    def test_negative_amount_rejected(self):
        s = PaymentRequestSerializer(data=self._payload(amount='-1.00'))
        self.assertFalse(s.is_valid())

    def test_zero_amount_rejected(self):
        s = PaymentRequestSerializer(data=self._payload(amount='0.00'))
        self.assertFalse(s.is_valid())

    def test_luhn_failure(self):
        s = PaymentRequestSerializer(data=self._payload(card_number=INVALID_LUHN))
        self.assertFalse(s.is_valid())

    def test_expired_card_rejected(self):
        s = PaymentRequestSerializer(data=self._payload(expiration_year=2020))
        self.assertFalse(s.is_valid())


class RefundRequestSerializerTest(TestCase):

    def test_empty_body_is_valid(self):
        """Empty body → full refund, which is allowed."""
        s = RefundRequestSerializer(data={})
        self.assertTrue(s.is_valid(), s.errors)

    def test_partial_amount(self):
        s = RefundRequestSerializer(data={'amount': '25.00'})
        self.assertTrue(s.is_valid())

    def test_zero_amount_rejected(self):
        s = RefundRequestSerializer(data={'amount': '0.00'})
        self.assertFalse(s.is_valid())


# ===========================================================================
# Helper function tests
# ===========================================================================

class SimulateAuthorizationTest(TestCase):

    def test_approved(self):
        approved, reason = _simulate_authorization(VISA_NUMBER, Decimal('50.00'))
        self.assertTrue(approved)
        self.assertEqual(reason, '')

    def test_declined_insuf_funds(self):
        approved, reason = _simulate_authorization(DECLINE_INSUF, Decimal('50.00'))
        self.assertFalse(approved)
        self.assertIn('funds', reason.lower())

    def test_declined_by_issuer(self):
        approved, reason = _simulate_authorization(DECLINE_ISSUER, Decimal('50.00'))
        self.assertFalse(approved)
        self.assertIn('declined', reason.lower())

    def test_declined_over_limit(self):
        approved, reason = _simulate_authorization(VISA_NUMBER, Decimal('9001.00'))
        self.assertFalse(approved)
        self.assertIn('limit', reason.lower())

    def test_auth_code_format(self):
        code = _generate_auth_code()
        self.assertEqual(len(code), 12)
        self.assertTrue(code.isalnum())


# ===========================================================================
# API / View tests
# ===========================================================================

class CardAPITest(TestCase):

    def setUp(self):
        self.client = Client()
        self.tokenise_url = '/api/cards/'

    def _post_json(self, url, data):
        return self.client.post(
            url, json.dumps(data), content_type='application/json'
        )

    def test_tokenise_valid_card(self):
        payload = {
            'cardholder_name': 'Jane Doe',
            'number': VISA_NUMBER,
            'expiration_month': 12,
            'expiration_year': 2030,
            'cvv': '123',
        }
        resp = self._post_json(self.tokenise_url, payload)
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body['last_four'], '1111')
        self.assertEqual(body['brand'], 'Visa')
        self.assertNotIn('cvv', body)
        self.assertNotIn('number', body)

    def test_tokenise_invalid_luhn(self):
        payload = {
            'cardholder_name': 'Bad Card',
            'number': INVALID_LUHN,
            'expiration_month': 12,
            'expiration_year': 2030,
            'cvv': '123',
        }
        resp = self._post_json(self.tokenise_url, payload)
        self.assertEqual(resp.status_code, 400)

    def test_list_cards(self):
        # Create one card first
        self._post_json(self.tokenise_url, {
            'cardholder_name': 'Test',
            'number': VISA_NUMBER,
            'expiration_month': 12,
            'expiration_year': 2030,
            'cvv': '123',
        })
        resp = self.client.get(self.tokenise_url)
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)
        self.assertGreaterEqual(len(resp.json()), 1)

    def test_get_card_detail(self):
        create_resp = self._post_json(self.tokenise_url, {
            'cardholder_name': 'Detail Test',
            'number': VISA_NUMBER,
            'expiration_month': 12,
            'expiration_year': 2030,
            'cvv': '123',
        })
        card_id = create_resp.json()['id']
        resp = self.client.get(f'/api/cards/{card_id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['id'], card_id)

    def test_get_card_not_found(self):
        resp = self.client.get(f'/api/cards/{uuid.uuid4()}/')
        self.assertEqual(resp.status_code, 404)

    def test_delete_card_no_transactions(self):
        create_resp = self._post_json(self.tokenise_url, {
            'cardholder_name': 'Del Test',
            'number': VISA_NUMBER,
            'expiration_month': 12,
            'expiration_year': 2030,
            'cvv': '123',
        })
        card_id = create_resp.json()['id']
        resp = self.client.delete(f'/api/cards/{card_id}/')
        self.assertEqual(resp.status_code, 204)

    def test_delete_card_with_transactions_blocked(self):
        # Charge first so card has a transaction
        charge_resp = self._post_json('/api/payments/charge/', VALID_CARD_PAYLOAD)
        self.assertIn(charge_resp.status_code, (201, 402))
        card_id = charge_resp.json()['card']['id']
        resp = self.client.delete(f'/api/cards/{card_id}/')
        self.assertEqual(resp.status_code, 409)


class ChargeAPITest(TestCase):

    def setUp(self):
        self.client = Client()
        self.charge_url = '/api/payments/charge/'

    def _charge(self, overrides=None):
        payload = dict(VALID_CARD_PAYLOAD)
        if overrides:
            payload.update(overrides)
        return self.client.post(
            self.charge_url, json.dumps(payload), content_type='application/json'
        )

    def test_approved_charge(self):
        resp = self._charge()
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body['status'], 'approved')
        self.assertTrue(body['authorization_code'])
        self.assertEqual(body['transaction_type'], 'charge')

    def test_declined_insufficient_funds(self):
        resp = self._charge({'card_number': DECLINE_INSUF})
        self.assertEqual(resp.status_code, 402)
        body = resp.json()
        self.assertEqual(body['status'], 'declined')
        self.assertFalse(body['authorization_code'])
        self.assertIn('funds', body['failure_reason'].lower())

    def test_declined_by_issuer(self):
        resp = self._charge({'card_number': DECLINE_ISSUER})
        self.assertEqual(resp.status_code, 402)
        self.assertEqual(resp.json()['status'], 'declined')

    def test_declined_over_limit(self):
        resp = self._charge({'amount': '9500.00'})
        self.assertEqual(resp.status_code, 402)
        self.assertIn('limit', resp.json()['failure_reason'].lower())

    def test_invalid_card_number_rejected(self):
        resp = self._charge({'card_number': INVALID_LUHN})
        self.assertEqual(resp.status_code, 400)

    def test_expired_card_rejected(self):
        resp = self._charge({'expiration_year': 2020, 'expiration_month': 1})
        self.assertEqual(resp.status_code, 400)

    def test_missing_amount_rejected(self):
        payload = dict(VALID_CARD_PAYLOAD)
        del payload['amount']
        resp = self.client.post(
            self.charge_url, json.dumps(payload), content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)

    def test_transaction_recorded_in_db(self):
        self._charge()
        self.assertEqual(Transaction.objects.filter(transaction_type='charge').count(), 1)


class RefundAPITest(TestCase):

    def setUp(self):
        self.client = Client()
        # Create an approved charge to refund
        resp = self.client.post(
            '/api/payments/charge/',
            json.dumps(VALID_CARD_PAYLOAD),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        self.charge = resp.json()
        self.charge_id = self.charge['id']
        self.refund_url = f'/api/payments/{self.charge_id}/refund/'

    def _refund(self, data=None):
        return self.client.post(
            self.refund_url,
            json.dumps(data or {}),
            content_type='application/json',
        )

    def test_full_refund(self):
        resp = self._refund()
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body['transaction_type'], 'refund')
        self.assertEqual(body['status'], 'approved')
        self.assertEqual(Decimal(body['amount']), Decimal(self.charge['amount']))

    def test_partial_refund(self):
        resp = self._refund({'amount': '10.00', 'reason': 'Partial return'})
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(Decimal(body['amount']), Decimal('10.00'))

    def test_refund_marks_original_as_refunded(self):
        self._refund()  # Full refund
        original = Transaction.objects.get(pk=self.charge_id)
        self.assertEqual(original.status, 'refunded')

    def test_partial_refund_does_not_change_original_status(self):
        self._refund({'amount': '1.00'})
        original = Transaction.objects.get(pk=self.charge_id)
        # Still approved because not fully refunded
        self.assertEqual(original.status, 'approved')

    def test_over_refund_rejected(self):
        resp = self._refund({'amount': '999.99'})
        self.assertEqual(resp.status_code, 409)

    def test_refund_not_found(self):
        resp = self.client.post(
            f'/api/payments/{uuid.uuid4()}/refund/',
            json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 404)

    def test_refund_on_declined_transaction_rejected(self):
        # Create a declined charge
        payload = dict(VALID_CARD_PAYLOAD, card_number=DECLINE_INSUF)
        resp = self.client.post(
            '/api/payments/charge/',
            json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 402)
        declined_id = resp.json()['id']
        refund_resp = self.client.post(
            f'/api/payments/{declined_id}/refund/',
            json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(refund_resp.status_code, 409)


class VoidAPITest(TestCase):

    def setUp(self):
        self.client = Client()
        resp = self.client.post(
            '/api/payments/charge/',
            json.dumps(VALID_CARD_PAYLOAD),
            content_type='application/json',
        )
        self.charge_id = resp.json()['id']

    def test_void_approved_transaction(self):
        resp = self.client.post(
            f'/api/payments/{self.charge_id}/void/',
            json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'voided')

    def test_void_already_voided_rejected(self):
        self.client.post(
            f'/api/payments/{self.charge_id}/void/',
            json.dumps({}),
            content_type='application/json',
        )
        # Second void should fail
        resp = self.client.post(
            f'/api/payments/{self.charge_id}/void/',
            json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 409)

    def test_void_not_found(self):
        resp = self.client.post(
            f'/api/payments/{uuid.uuid4()}/void/',
            json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 404)


class PaymentStatusAPITest(TestCase):

    def setUp(self):
        self.client = Client()
        resp = self.client.post(
            '/api/payments/charge/',
            json.dumps(VALID_CARD_PAYLOAD),
            content_type='application/json',
        )
        self.txn = resp.json()

    def test_payment_status_returns_correct_fields(self):
        resp = self.client.get(f'/api/payments/{self.txn["id"]}/status/')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn('status', body)
        self.assertIn('authorization_code', body)
        self.assertIn('amount', body)
        self.assertIn('currency', body)
        self.assertIn('transaction_type', body)
        self.assertIn('updated_at', body)

    def test_payment_status_not_found(self):
        resp = self.client.get(f'/api/payments/{uuid.uuid4()}/status/')
        self.assertEqual(resp.status_code, 404)


class TransactionListAPITest(TestCase):

    def setUp(self):
        self.client = Client()
        # Create two charges: one approved, one declined
        self.client.post(
            '/api/payments/charge/',
            json.dumps(VALID_CARD_PAYLOAD),
            content_type='application/json',
        )
        self.client.post(
            '/api/payments/charge/',
            json.dumps(dict(VALID_CARD_PAYLOAD, card_number=DECLINE_INSUF)),
            content_type='application/json',
        )

    def test_list_all_transactions(self):
        resp = self.client.get('/api/transactions/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 2)

    def test_filter_by_status_approved(self):
        resp = self.client.get('/api/transactions/?status=approved')
        self.assertEqual(resp.status_code, 200)
        for txn in resp.json():
            self.assertEqual(txn['status'], 'approved')

    def test_filter_by_status_declined(self):
        resp = self.client.get('/api/transactions/?status=declined')
        self.assertEqual(resp.status_code, 200)
        for txn in resp.json():
            self.assertEqual(txn['status'], 'declined')

    def test_transaction_detail(self):
        list_resp = self.client.get('/api/transactions/')
        txn_id = list_resp.json()[0]['id']
        resp = self.client.get(f'/api/transactions/{txn_id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['id'], txn_id)

    def test_transaction_detail_not_found(self):
        resp = self.client.get(f'/api/transactions/{uuid.uuid4()}/')
        self.assertEqual(resp.status_code, 404)
