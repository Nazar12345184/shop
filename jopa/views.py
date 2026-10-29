import json
import logging
import hashlib
import hmac
import time
import uuid
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.db.models import Avg, Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import GameReviewForm, GameSubmissionForm, ProfileForm, RegistrationForm, SiteGameAdminForm, SiteUserAccessForm
from .models import CatalogType, Favorite, GamePurchase, GameReview, GameSubmission, SiteNotification, TelegramProfile, games

logger = logging.getLogger(__name__)


def home(request):
    search_query = request.GET.get('q', '').strip()[:100]
    selected_kind = request.GET.get('kind', '').strip()
    selected_genre = request.GET.get('genre', '').strip()[:80]
    min_price = request.GET.get('min_price', '').strip()
    max_price = request.GET.get('max_price', '').strip()
    ordering = request.GET.get('sort', 'newest')
    valid_kinds = {value for value, _label in CatalogType.choices}

    games_queryset = games.objects.all()
    if search_query:
        games_queryset = games_queryset.filter(
            Q(name__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(developer__icontains=search_query)
            | Q(genre__icontains=search_query)
        )
    if selected_kind in valid_kinds:
        games_queryset = games_queryset.filter(kind=selected_kind)
    if selected_genre:
        games_queryset = games_queryset.filter(genre__iexact=selected_genre)
    try:
        min_value = Decimal(min_price) if min_price else None
        if min_value is not None and (not min_value.is_finite() or min_value < 0):
            raise InvalidOperation
    except InvalidOperation:
        min_price, min_value = '', None
    try:
        max_value = Decimal(max_price) if max_price else None
        if max_value is not None and (not max_value.is_finite() or max_value < 0):
            raise InvalidOperation
    except InvalidOperation:
        max_price, max_value = '', None
    if min_value is not None and max_value is not None and max_value < min_value:
        min_price = max_price = ''
        min_value = max_value = None
    if min_value is not None:
        games_queryset = games_queryset.filter(price__gte=min_value)
    if max_value is not None:
        games_queryset = games_queryset.filter(price__lte=max_value)

    games_list = games_queryset.annotate(
        sales_count=Count(
            'purchases',
            distinct=True,
            filter=Q(
                purchases__status=GamePurchase.Status.PAID,
                purchases__amount__gt=0,
            ),
        ),
        average_rating=Avg('reviews__rating'),
        review_count=Count('reviews', distinct=True),
    )
    sort_options = {'newest': '-pk', 'price_low': 'price', 'price_high': '-price', 'popular': '-sales_count', 'rating': '-average_rating'}
    if ordering not in sort_options:
        ordering = 'newest'
    games_list = games_list.order_by(sort_options[ordering], '-pk')
    owned_ids = set()
    favorite_ids = set()
    if request.user.is_authenticated:
        owned_ids = set(GamePurchase.objects.filter(user=request.user, status=GamePurchase.Status.PAID).values_list('game_id', flat=True))
        favorite_ids = set(Favorite.objects.filter(user=request.user).values_list('game_id', flat=True))
    return render(request, 'index.html', {
        'games': games_list,
        'owned_ids': owned_ids,
        'search_query': search_query,
        'selected_kind': selected_kind if selected_kind in valid_kinds else '',
        'kind_choices': CatalogType.choices,
        'genres': games.objects.exclude(genre='').order_by('genre').values_list('genre', flat=True).distinct(),
        'selected_genre': selected_genre,
        'min_price': min_price,
        'max_price': max_price,
        'ordering': ordering,
        'favorite_ids': favorite_ids,
    })


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
    purchase_price = game.current_price
    if purchase_price is None or purchase_price <= 0:
        GamePurchase.objects.get_or_create(
            user=request.user,
            game=game,
            status=GamePurchase.Status.PAID,
            defaults={
                'order_reference': f'free-{request.user.pk}-{game.pk}',
                'amount': 0,
                'paid_at': timezone.now(),
            },
        )
        messages.success(request, 'Гру додано до бібліотеки без оплати.')
        return redirect('library')
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
        amount=purchase_price,
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
    favorites = Favorite.objects.filter(user=request.user).select_related('game')
    return render(request, 'library.html', {'purchases': purchases, 'favorites': favorites})


@login_required
@require_POST
def toggle_favorite(request, pk):
    game = get_object_or_404(games, pk=pk)
    favorite, created = Favorite.objects.get_or_create(user=request.user, game=game)
    if not created:
        favorite.delete()
    next_url = request.POST.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)
    return redirect('home')


@login_required
@require_POST
def submit_review(request, pk):
    game = get_object_or_404(games, pk=pk)
    review = GameReview.objects.filter(user=request.user, game=game).first()
    form = GameReviewForm(request.POST, instance=review)
    if form.is_valid():
        saved_review = form.save(commit=False)
        saved_review.user = request.user
        saved_review.game = game
        saved_review.save()
        messages.success(request, 'Відгук збережено.')
    else:
        messages.error(request, 'Перевір оцінку та текст відгуку.')
    return redirect('game_detail', pk=game.pk)


@login_required
def profile(request):
    profile_obj, _created = TelegramProfile.objects.get_or_create(
        user=request.user,
        defaults={'telegram_username': f'user_{request.user.pk}'},
    )
    form = ProfileForm(request.POST or None, instance=profile_obj, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Профіль збережено.')
        return redirect('profile')
    submissions = GameSubmission.objects.filter(submitter_user=request.user)
    purchases = GamePurchase.objects.filter(user=request.user).select_related('game')
    notifications = SiteNotification.objects.filter(user=request.user)
    return render(request, 'profile.html', {
        'form': form,
        'submissions': submissions,
        'purchases': purchases,
        'favorites_count': Favorite.objects.filter(user=request.user).count(),
        'reviews_count': GameReview.objects.filter(user=request.user).count(),
        'notifications': notifications,
        'unread_notifications': notifications.filter(read_at__isnull=True).count(),
    })


def author_detail(request, pk):
    author = get_object_or_404(get_user_model(), pk=pk)
    author_games = games.objects.filter(author=author).annotate(
        sales_count=Count('purchases', distinct=True, filter=Q(purchases__status=GamePurchase.Status.PAID, purchases__amount__gt=0)),
        average_rating=Avg('reviews__rating'),
        review_count=Count('reviews', distinct=True),
    )
    if not author_games.exists():
        from django.http import Http404
        raise Http404
    return render(request, 'author_detail.html', {'author': author, 'games': author_games})


@login_required
@require_POST
def read_notification(request, pk):
    notification = get_object_or_404(SiteNotification, pk=pk, user=request.user)
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=('read_at',))
    return redirect('profile')


@user_passes_test(lambda user: user.is_active and user.is_staff)
def manage_site(request):
    all_games = games.objects.order_by('name')
    selected_id = request.GET.get('game_id') or request.POST.get('game_id')
    selected_game = games.objects.filter(pk=selected_id).first() if selected_id else all_games.first()
    game_form = SiteGameAdminForm(instance=selected_game)
    access_overrides = {}

    if request.method == 'POST' and request.POST.get('action') == 'save_game':
        selected_game = get_object_or_404(games, pk=request.POST.get('game_id'))
        game_form = SiteGameAdminForm(request.POST, request.FILES, instance=selected_game)
        if game_form.is_valid():
            saved_game = game_form.save()
            messages.success(request, f'Зміни для «{saved_game.name}» збережено.')
            return redirect(f'{reverse("manage_site")}?game_id={saved_game.pk}')

    if request.method == 'POST' and request.POST.get('action') == 'save_user':
        if not request.user.is_superuser:
            return HttpResponse(status=403)
        target_user = get_object_or_404(get_user_model(), pk=request.POST.get('user_id'))
        access_form = SiteUserAccessForm(request.POST, instance=target_user)
        if access_form.is_valid():
            if access_form.cleaned_data['is_superuser'] and not access_form.cleaned_data['is_staff']:
                access_form.add_error('is_staff', 'Суперкористувачу потрібен доступ до адмінки.')
            elif target_user.pk == request.user.pk and not all((
                access_form.cleaned_data['is_active'],
                access_form.cleaned_data['is_staff'],
                access_form.cleaned_data['is_superuser'],
            )):
                access_form.add_error(None, 'Не можна вимкнути власний доступ суперкористувача.')
            else:
                access_form.save()
                messages.success(request, f'Права користувача {target_user.username} оновлено.')
                return redirect(f'{reverse("manage_site")}?game_id={selected_id or ""}#users')
        access_overrides[target_user.pk] = access_form

    users = get_user_model().objects.order_by('username') if request.user.is_superuser else []
    access_rows = [
        (user, access_overrides.get(user.pk) or SiteUserAccessForm(instance=user))
        for user in users
    ]
    return render(request, 'manage.html', {
        'games': all_games,
        'selected_game': selected_game,
        'game_form': game_form,
        'access_rows': access_rows,
        'can_manage_users': request.user.is_superuser,
    })


@login_required
@require_POST
def add_free_game(request, pk):
    game = get_object_or_404(games, pk=pk)
    if game.current_price is not None and game.current_price > 0:
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
    game = get_object_or_404(
        games.objects.annotate(
            sales_count=Count(
                'purchases',
                distinct=True,
                filter=Q(
                    purchases__status=GamePurchase.Status.PAID,
                    purchases__amount__gt=0,
                ),
            ),
            average_rating=Avg('reviews__rating'),
            review_count=Count('reviews', distinct=True),
        ),
        pk=pk,
    )
    review = None
    is_favorite = False
    if request.user.is_authenticated:
        review = GameReview.objects.filter(user=request.user, game=game).first()
        is_favorite = Favorite.objects.filter(user=request.user, game=game).exists()
    return render(request, 'game_detail.html', {
        'game': game,
        'reviews': game.reviews.select_related('user').all(),
        'review_form': GameReviewForm(instance=review),
        'is_favorite': is_favorite,
    })


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
            if request.user.is_authenticated:
                submission.submitter_user = request.user
                submission.save(update_fields=('submitter_user',))
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
