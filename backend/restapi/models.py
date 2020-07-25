from django.db import models

# Create your models here.
class Cards(models.Model):
    number = models.IntegerField()
    expirationMonth = models.IntegerField()
    expirationYear = models.IntegerField()
    cvv = models.IntegerField()

class Transaction(models.Model):
    ammount = models.IntegerField()
    currency = models.CharField(max_length = 10)
    type = models.CharField(max_length = 20)
    card = models.ForeignKey(Cards,on_delete=models.CASCADE)
    status = models.CharField(max_length = 20)
    authorization_code = models.CharField(max_length=20)
    time = models.DateTimeField()
