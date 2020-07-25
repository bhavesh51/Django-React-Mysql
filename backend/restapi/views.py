from django.shortcuts import render

# Create your views here.
from django.http.response import JsonResponse
from rest_framework.parsers import JSONParser 
from rest_framework import status
 
from restapi.models import Cards,Transaction
from restapi.serializers import cardSerializer, transactionSerialization
from rest_framework.decorators import api_view

@api_view(['GET'])
def cards(request):
    if request.method == 'GET':
        cards = Cards.objects.all()
        number = request.GET.get('number', None)
        cards_serializer = cardSerializer(cards, many=True)
        return JsonResponse(cards_serializer.data, safe=False)
    return JsonResponse({"name":"bhavesh"})
 


@api_view(['POST'])
def card_list(request):
    card_data = JSONParser().parse(request)
    #transactionSerialization = transactionSerialization(data=card_data)
    # if transactionSerialization.is_valid():
    #     transactionSerialization.save()
    #return JsonResponse(transactionSerialization.data, status=status.HTTP_201_CREATED) 
    #return JsonResponse(transactionSerialization.errors, status=status.HTTP_400_BAD_REQUEST)
    #card_data = JSONParser().parse(request)
    return JsonResponse(card_data)