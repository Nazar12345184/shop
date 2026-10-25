import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import GameSubmissionForm
from .models import GameSubmission, games

logger = logging.getLogger(__name__)


def home(request):
    games_list = games.objects.all()
    return render(request, 'index.html', {'games': games_list})


def game_detail(request, pk):
    game = get_object_or_404(games, pk=pk)
    return render(request, 'game_detail.html', {'game': game})


def send_telegram_notification(text):
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        raise RuntimeError('Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env.')

    payload = urlencode({'chat_id': chat_id, 'text': text}).encode('utf-8')
    request = Request(
        f'https://api.telegram.org/bot{token}/sendMessage',
        data=payload,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    try:
        with urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        try:
            error_data = json.loads(exc.read().decode('utf-8'))
            detail = error_data.get('description', str(exc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            detail = str(exc)
        raise RuntimeError(f'Telegram API error ({exc.code}): {detail}') from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f'Could not connect to Telegram: {exc}') from exc
    if not result.get('ok'):
        raise RuntimeError(f"Telegram rejected the message: {result.get('description', 'unknown error')}")


def submit_game(request):
    if request.method == 'POST':
        form = GameSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            submission = form.save()
            review_url = request.build_absolute_uri(
                reverse('admin:jopa_gamesubmission_change', args=(submission.pk,))
            )
            notification = (
                f'Нова заявка на гру: {submission.name}\n'
                f'Автор: {submission.submitter_name} ({submission.submitter_telegram})\n\n'
                f'Переглянути заявку в адмінці: {review_url}'
            )
            try:
                if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
                    send_telegram_notification(notification)
                else:
                    raise RuntimeError('Configure Telegram in .env to receive submission notifications.')
                messages.success(request, 'Заявку збережено на перевірку. Сповіщення надіслано у Telegram.')
            except Exception:
                logger.exception('Could not send game submission notification.')
                messages.warning(
                    request,
                    'Заявку збережено на перевірку, але сповіщення не надіслалося. Перевірте налаштування Telegram.',
                )
            return redirect('submit_game')
    else:
        form = GameSubmissionForm()

    return render(request, 'submit_game.html', {'form': form})
