from django.urls import path
from .views import game_detail, home, submit_game

urlpatterns = [
    path('', home, name='home'),
    path('main/', home, name='main'),
    path('game/<int:pk>/', game_detail, name='game_detail'),
    path('submit-game/', submit_game, name='submit_game'),
]
