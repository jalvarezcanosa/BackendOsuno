"""
URL configuration for OsunoAPI project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from django.urls import path

from osunorest01app import endpoints

urlpatterns = [
    path('admin/', admin.site.urls),
    path('room', endpoints.create_room),
    path('health/', endpoints.health_check),
    path('user', endpoints.create_user),
    path('room/<str:room_code>/status', endpoints.get_room_status),##debe ser la misma url que el método de join_room
    path('game/<str:room_code>/tableCard/', endpoints.play_card),
# Endpoints del juego de cartas
    path('game/<str:room_code>/deck', endpoints.draw_card),
    path('game/<str:room_code>/hand', endpoints.get_hand),
    path('game/<str:room_code>/state', endpoints.get_game_state),
    path('game/<str:room_code>/playable', endpoints.get_playable_cards),
]