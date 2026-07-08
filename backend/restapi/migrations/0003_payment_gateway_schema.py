# Generated migration — replaces previous migrations with the full schema.
# Run: python manage.py migrate

import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('restapi', '0002_auto_20200726_0425'),
    ]

    operations = [
        # ----------------------------------------------------------------
        # Drop old tables and recreate with the corrected schema.
        # ----------------------------------------------------------------
        migrations.DeleteModel(name='Transaction'),
        migrations.DeleteModel(name='Cards'),

        # Cards (re-created)
        migrations.CreateModel(
            name='Cards',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('cardholder_name', models.CharField(max_length=100)),
                ('number', models.CharField(max_length=16)),
                ('last_four', models.CharField(editable=False, max_length=4)),
                ('expiration_month', models.IntegerField()),
                ('expiration_year', models.IntegerField()),
                ('cvv', models.CharField(max_length=4)),
                ('brand', models.CharField(blank=True, default='', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'cards',
                'ordering': ['-created_at'],
            },
        ),

        # Transaction (re-created)
        migrations.CreateModel(
            name='Transaction',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('currency', models.CharField(default='USD', max_length=3)),
                ('transaction_type', models.CharField(
                    choices=[
                        ('charge', 'Charge'),
                        ('refund', 'Refund'),
                        ('void', 'Void'),
                        ('authorization', 'Authorization'),
                        ('capture', 'Capture'),
                    ],
                    default='charge',
                    max_length=20,
                )),
                ('card', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='transactions',
                    to='restapi.cards',
                )),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('approved', 'Approved'),
                        ('declined', 'Declined'),
                        ('voided', 'Voided'),
                        ('refunded', 'Refunded'),
                        ('failed', 'Failed'),
                    ],
                    default='pending',
                    max_length=20,
                )),
                ('authorization_code', models.CharField(blank=True, default='', max_length=32)),
                ('description', models.CharField(blank=True, default='', max_length=255)),
                ('merchant_reference', models.CharField(blank=True, default='', max_length=100)),
                ('failure_reason', models.CharField(blank=True, default='', max_length=255)),
                ('parent_transaction', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='child_transactions',
                    to='restapi.transaction',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'transactions',
                'ordering': ['-created_at'],
            },
        ),
    ]
