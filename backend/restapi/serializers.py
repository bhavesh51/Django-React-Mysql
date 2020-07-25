from rest_framework import serializers
from restapi.models import Cards, Transaction

class cardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cards
        field = (
            'id',
            'number',
            'expirationMonth',
            'expirationYear',
            'cvv'
        )

class transactionSerialization(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        field = (
            'id',
            'ammount',
            'currency',
            'type',
            'status',
            'authorization_code',
            'time',
            'card'
        )