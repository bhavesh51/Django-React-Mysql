from django.conf.urls import url 
from restapi import views 
 
urlpatterns = [ 
    url(r'^api/card$', views.cards),
    url(r'^api/card_info$', views.card_list)  
]