from django.urls import include, path
from .views import add_free_game, author_detail, buy_game, download_game_file, game_detail, home, library, manage_site, profile, read_notification, register, submit_game, submit_review, toggle_favorite, upload_game_folder_chunk, wayforpay_callback

urlpatterns = [
    path('', home, name='home'),
    path('main/', home, name='main'),
    path('game/<int:pk>/', game_detail, name='game_detail'),
    path('submit-game/', submit_game, name='submit_game'),
    path('accounts/register/', register, name='register'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('library/', library, name='library'),
    path('library/download/<int:pk>/', download_game_file, name='download_game_file'),
    path('profile/', profile, name='profile'),
    path('manage/', manage_site, name='manage_site'),
    path('manage/upload-folder-chunk/', upload_game_folder_chunk, name='upload_game_folder_chunk'),
    path('author/<int:pk>/', author_detail, name='author_detail'),
    path('notifications/<int:pk>/read/', read_notification, name='read_notification'),
    path('favorite/<int:pk>/toggle/', toggle_favorite, name='toggle_favorite'),
    path('game/<int:pk>/review/', submit_review, name='submit_review'),
    path('buy/<int:pk>/', buy_game, name='buy_game'),
    path('library/add-free/<int:pk>/', add_free_game, name='add_free_game'),
    path('payments/wayforpay/callback/', wayforpay_callback, name='wayforpay_callback'),
]
