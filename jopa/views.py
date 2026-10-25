import json
import logging
import hashlib
import hmac
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import GameSubmissionForm, RegistrationForm
from .models import GamePurchase, GameSubmission, games

logger = logging.getLogger(__name__)


def home(request):
    games_list = games.objects.all()
    owned_ids = set()
    if request.user.is_authenticated:
        owned_ids = set(GamePurchase.objects.filter(user=request.user, status=GamePurchase.Status.PAID).values_list('game_id', flat=True))
    return render(request, 'index.html', {'games': games_list, 'owned_ids': owned_ids})


def _wayforpay_signature(fields):
    message = ';'.join(str(value) for value in fields)
    return hmac.new(settings.WAYFORPAY_SECRET_KEY.encode(), message.encode('utf-8'), hashlib.md5).hexdigest()


def notify_purchase_in_telegram(purchase):
    if purchase.telegram_notified_at:
        return

    profile = getattr(purchase.user, 'telegram_profile', None)
    telegram_username = f'@{profile.telegram_username}' if profile else 'не вказаний'
    buyer_name = purchase.user.get_full_name().strip() or purchase.user.username
    notification = (
        '✅ Нова покупка гри\n'
        f'Гра: {purchase.game.name}\n'
        f'Покупець: {buyer_name} (логін: {purchase.user.username})\n'
        f'Telegram: {telegram_username}\n'
        f'Сума: {purchase.amount:.2f} грн'
    )
    try:
        send_telegram_notification(notification)
    except Exception:
        logger.exception('Could not send Telegram notification for purchase %s.', purchase.order_reference)
        return

    purchase.telegram_notified_at = timezone.now()
    purchase.save(update_fields=('telegram_notified_at',))


@login_required
@require_POST
def buy_game(request, pk):
    game = get_object_or_404(games, pk=pk)
    if game.price is None or game.price <= 0:
        messages.error(request, 'Ця гра безкоштовна — додайте її до бібліотеки.')
        return redirect('home')
    if GamePurchase.objects.filter(user=request.user, game=game, status=GamePurchase.Status.PAID).exists():
        messages.info(request, 'Ця гра вже є у вашій бібліотеці.')
        return redirect('library')
    required = (settings.SITE_URL, settings.WAYFORPAY_MERCHANT_ACCOUNT, settings.WAYFORPAY_SECRET_KEY, settings.WAYFORPAY_MERCHANT_DOMAIN)
    if not all(required):
        messages.error(request, 'Оплата ще не налаштована. Потрібні облікові дані WayForPay та публічна адреса сайту в .env.')
        return redirect('home')

    order = GamePurchase.objects.create(
        user=request.user,
        game=game,
        amount=game.price,
        order_reference=f'game-{game.pk}-{uuid.uuid4().hex}',
    )
    order_date = int(time.time())
    product_names = [game.name]
    product_counts = [1]
    product_prices = [f'{order.amount:.2f}']
    signature_fields = [settings.WAYFORPAY_MERCHANT_ACCOUNT, settings.WAYFORPAY_MERCHANT_DOMAIN,
                        order.order_reference, order_date, f'{order.amount:.2f}', 'UAH',
                        *product_names, *product_counts, *product_prices]
    payload = {
        'transactionType': 'CREATE_INVOICE',
        'merchantAccount': settings.WAYFORPAY_MERCHANT_ACCOUNT,
        'merchantAuthType': 'SimpleSignature',
        'merchantDomainName': settings.WAYFORPAY_MERCHANT_DOMAIN,
        'merchantSignature': _wayforpay_signature(signature_fields),
        'apiVersion': 1,
        'language': 'UA',
        'serviceUrl': f'{settings.SITE_URL}{reverse("wayforpay_callback")}',
        'orderReference': order.order_reference,
        'orderDate': order_date,
        'amount': f'{order.amount:.2f}',
        'currency': 'UAH',
        'productName': product_names,
        'productCount': product_counts,
        'productPrice': product_prices,
        'clientEmail': request.user.email or None,
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    api_request = Request('https://api.wayforpay.com/api', data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
    try:
        with urlopen(api_request, timeout=20) as response:
            result = json.loads(response.read().decode('utf-8'))
        invoice_url = result.get('invoiceUrl')
        if not invoice_url:
            raise RuntimeError(result.get('reason', 'WayForPay не повернув адресу оплати.'))
        return redirect(invoice_url)
    except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as exc:
        logger.exception('Could not create WayForPay invoice for order %s.', order.order_reference)
        messages.error(request, f'Не вдалося створити рахунок WayForPay: {exc}')
        return redirect('home')


@csrf_exempt
@require_POST
def wayforpay_callback(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponse(status=400)
    order_reference = str(data.get('orderReference', ''))
    order = GamePurchase.objects.filter(order_reference=order_reference).first()
    if order is None:
        return HttpResponse(status=404)
    fields = [data.get('merchantAccount', ''), data.get('orderReference', ''), data.get('amount', ''),
              data.get('currency', ''), data.get('authCode', ''), data.get('cardPan', ''),
              data.get('transactionStatus', ''), data.get('reasonCode', '')]
    expected = _wayforpay_signature(fields)
    if not hmac.compare_digest(str(data.get('merchantSignature', '')), expected):
        return HttpResponse(status=400)
    if data.get('merchantAccount') != settings.WAYFORPAY_MERCHANT_ACCOUNT:
        return HttpResponse(status=400)
    if data.get('transactionStatus') == 'Approved':
        from decimal import Decimal, InvalidOperation
        try:
            callback_amount = Decimal(str(data.get('amount')))
        except InvalidOperation:
            return HttpResponse(status=400)
        if str(data.get('currency')) != 'UAH' or callback_amount != order.amount:
            return HttpResponse(status=400)
        if order.status != GamePurchase.Status.PAID:
            order.status = GamePurchase.Status.PAID
            order.paid_at = timezone.now()
            order.save(update_fields=('status', 'paid_at'))
        notify_purchase_in_telegram(order)
    response_time = int(time.time())
    response_fields = [order_reference, 'accept', response_time]
    return JsonResponse({
        'orderReference': order_reference,
        'status': 'accept',
        'time': response_time,
        'signature': _wayforpay_signature(response_fields),
    })


@login_required
def library(request):
    purchases = GamePurchase.objects.filter(user=request.user, status=GamePurchase.Status.PAID).select_related('game')
    return render(request, 'library.html', {'purchases': purchases})


@login_required
@require_POST
def add_free_game(request, pk):
    game = get_object_or_404(games, pk=pk)
    if game.price is not None and game.price > 0:
        messages.error(request, 'Цю гру потрібно придбати через оплату.')
        return redirect('home')
    GamePurchase.objects.get_or_create(
        user=request.user,
        game=game,
        status=GamePurchase.Status.PAID,
        defaults={'order_reference': f'free-{request.user.pk}-{game.pk}', 'amount': 0, 'paid_at': timezone.now()},
    )
    return redirect('library')


def register(request):
    if request.user.is_authenticated:
        return redirect('home')
    form = RegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect('home')
    return render(request, 'registration/register.html', {'form': form})


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
                f'Категорія: {submission.get_kind_display()}\n'
                f'Нова пропозиція: {submission.name}\n'
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
