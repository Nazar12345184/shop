from django.urls import include, path
from .views import add_free_game, buy_game, game_detail, home, library, register, submit_game, wayforpay_callback

urlpatterns = [
    path('', home, name='home'),
    path('main/', home, name='main'),
    path('game/<int:pk>/', game_detail, name='game_detail'),
    path('submit-game/', submit_game, name='submit_game'),
    path('accounts/register/', register, name='register'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('library/', library, name='library'),
    path('buy/<int:pk>/', buy_game, name='buy_game'),
    path('library/add-free/<int:pk>/', add_free_game, name='add_free_game'),
    path('payments/wayforpay/callback/', wayforpay_callback, name='wayforpay_callback'),
]
