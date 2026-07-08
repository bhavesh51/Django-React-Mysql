from django.db import models
import uuid


class Cards(models.Model):
    """
    Represents a payment card stored (tokenised) in the system.
    Card numbers are stored masked; only the last 4 digits are retained
    after the initial save so that no raw PAN is persisted.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cardholder_name = models.CharField(max_length=100)
    # Full card number supplied on creation; stored as string to preserve
    # leading zeros and to allow masking.
    number = models.CharField(max_length=16)
    # After initial save we keep only the last 4 digits.
    last_four = models.CharField(max_length=4, editable=False)
    expiration_month = models.IntegerField()
    expiration_year = models.IntegerField()
    # CVV is never persisted after validation; stored temporarily during
    # request processing only (set to empty string after save).
    cvv = models.CharField(max_length=4)
    # Card brand derived from number prefix (Visa, Mastercard, Amex, etc.)
    brand = models.CharField(max_length=20, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cards'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Derive brand from IIN / BIN
        n = str(self.number).replace(' ', '')
        if n.startswith('4'):
            self.brand = 'Visa'
        elif n[:2] in ('51', '52', '53', '54', '55') or (
            2221 <= int(n[:4]) <= 2720
        ):
            self.brand = 'Mastercard'
        elif n[:2] in ('34', '37'):
            self.brand = 'Amex'
        elif n[:4] in ('6011',) or n[:2] == '65':
            self.brand = 'Discover'
        else:
            self.brand = 'Unknown'

        # Store only last 4 digits
        self.last_four = n[-4:]
        # Mask full number so raw PAN is not persisted
        self.number = '**** **** **** ' + self.last_four
        # CVV must never be persisted
        self.cvv = ''
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.brand} **** {self.last_four} ({self.cardholder_name})'


class Transaction(models.Model):
    """
    Represents a payment transaction tied to a card.
    """
    TRANSACTION_TYPES = [
        ('charge', 'Charge'),
        ('refund', 'Refund'),
        ('void', 'Void'),
        ('authorization', 'Authorization'),
        ('capture', 'Capture'),
    ]

    STATUSES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('declined', 'Declined'),
        ('voided', 'Voided'),
        ('refunded', 'Refunded'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES, default='charge')
    card = models.ForeignKey(Cards, on_delete=models.PROTECT, related_name='transactions')
    status = models.CharField(max_length=20, choices=STATUSES, default='pending')
    authorization_code = models.CharField(max_length=32, blank=True, default='')
    description = models.CharField(max_length=255, blank=True, default='')
    # Merchant / customer metadata
    merchant_reference = models.CharField(max_length=100, blank=True, default='')
    failure_reason = models.CharField(max_length=255, blank=True, default='')
    # Link a refund or void back to the original charge
    parent_transaction = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='child_transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'transactions'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.transaction_type.upper()} {self.currency} {self.amount} [{self.status}]'
