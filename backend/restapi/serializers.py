from rest_framework import serializers
from restapi.models import Cards, Transaction
from datetime import date


class CardCreateSerializer(serializers.Serializer):
    """
    Serializer used only during card tokenisation (POST /api/cards/).
    Accepts the full card number and CVV, validates them, but does NOT
    write raw data — the model.save() masks the PAN and drops the CVV.
    """
    cardholder_name = serializers.CharField(max_length=100)
    number = serializers.CharField(min_length=13, max_length=19)
    expiration_month = serializers.IntegerField(min_value=1, max_value=12)
    expiration_year = serializers.IntegerField(min_value=2000, max_value=2099)
    cvv = serializers.CharField(min_length=3, max_length=4)

    def validate_number(self, value):
        """Luhn algorithm check."""
        digits = value.replace(' ', '').replace('-', '')
        if not digits.isdigit():
            raise serializers.ValidationError('Card number must contain only digits.')
        total = 0
        reverse = digits[::-1]
        for i, d in enumerate(reverse):
            n = int(d)
            if i % 2 == 1:
                n *= 2
                if n > 9:
                    n -= 9
            total += n
        if total % 10 != 0:
            raise serializers.ValidationError('Invalid card number (Luhn check failed).')
        return digits

    def validate(self, data):
        """Check card is not expired."""
        today = date.today()
        exp_year = data['expiration_year']
        exp_month = data['expiration_month']
        if exp_year < today.year or (exp_year == today.year and exp_month < today.month):
            raise serializers.ValidationError('Card is expired.')
        return data

    def create(self, validated_data):
        return Cards.objects.create(**validated_data)


class CardSerializer(serializers.ModelSerializer):
    """Read-only serializer for returning card info (no PAN, no CVV)."""

    class Meta:
        model = Cards
        fields = (
            'id',
            'cardholder_name',
            'last_four',
            'brand',
            'expiration_month',
            'expiration_year',
            'created_at',
        )
        read_only_fields = fields


class TransactionSerializer(serializers.ModelSerializer):
    """Full transaction serializer for reads."""
    card = CardSerializer(read_only=True)
    card_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Transaction
        fields = (
            'id',
            'amount',
            'currency',
            'transaction_type',
            'card',
            'card_id',
            'status',
            'authorization_code',
            'description',
            'merchant_reference',
            'failure_reason',
            'parent_transaction',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'id', 'status', 'authorization_code', 'failure_reason',
            'created_at', 'updated_at',
        )


class PaymentRequestSerializer(serializers.Serializer):
    """
    Incoming payload for POST /api/payments/charge/.
    Mirrors what a real payment gateway (Stripe, Braintree, etc.) accepts.
    """
    # Card details (inline — card is tokenised on the fly)
    cardholder_name = serializers.CharField(max_length=100)
    card_number = serializers.CharField(min_length=13, max_length=19)
    expiration_month = serializers.IntegerField(min_value=1, max_value=12)
    expiration_year = serializers.IntegerField(min_value=2000, max_value=2099)
    cvv = serializers.CharField(min_length=3, max_length=4)

    # Payment details
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    currency = serializers.CharField(max_length=3, default='USD')
    description = serializers.CharField(max_length=255, required=False, default='')
    merchant_reference = serializers.CharField(max_length=100, required=False, default='')

    def validate_card_number(self, value):
        digits = value.replace(' ', '').replace('-', '')
        if not digits.isdigit():
            raise serializers.ValidationError('Card number must contain only digits.')
        total = 0
        reverse = digits[::-1]
        for i, d in enumerate(reverse):
            n = int(d)
            if i % 2 == 1:
                n *= 2
                if n > 9:
                    n -= 9
            total += n
        if total % 10 != 0:
            raise serializers.ValidationError('Invalid card number (Luhn check failed).')
        return digits

    def validate(self, data):
        today = date.today()
        if data['expiration_year'] < today.year or (
            data['expiration_year'] == today.year and data['expiration_month'] < today.month
        ):
            raise serializers.ValidationError({'card': 'Card is expired.'})
        return data


class RefundRequestSerializer(serializers.Serializer):
    """Payload for POST /api/payments/<id>/refund/."""
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0.01, required=False
    )
    reason = serializers.CharField(max_length=255, required=False, default='Customer requested refund')
