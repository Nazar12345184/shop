from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.conf import settings
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP


class CatalogType(models.TextChoices):
    GAME = 'game', 'Гра'
    PROJECT = 'project', 'Проєкт'
    SERVICE = 'service', 'Послуга'
    OTHER = 'other', 'Інше'


class games(models.Model):
    kind = models.CharField(max_length=12, choices=CatalogType.choices, default=CatalogType.GAME)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255)
    release_date = models.DateField(blank=True, null=True)
    developer = models.CharField(max_length=100, blank=True)
    genre = models.CharField(max_length=80, blank=True)
    system_requirements = models.TextField(blank=True)
    contact_telegram = models.CharField(max_length=100, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='published_games',
    )
    photo = models.ImageField(upload_to='static/img/', blank=True, null=True)
    link = models.URLField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    discount_percent = models.PositiveSmallIntegerField(
        'Знижка, %',
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='0 — без знижки, 100 — безкоштовно.',
    )
    discount_starts_at = models.DateTimeField('Початок знижки (UTC)', blank=True, null=True)
    discount_ends_at = models.DateTimeField('Кінець знижки (UTC)', blank=True, null=True)

    @property
    def discount_active(self):
        now = timezone.now()
        return (
            self.price is not None
            and self.price > 0
            and self.discount_percent > 0
            and (self.discount_starts_at is None or self.discount_starts_at <= now)
            and (self.discount_ends_at is None or self.discount_ends_at > now)
        )

    @property
    def current_price(self):
        if self.price is None or not self.discount_active:
            return self.price
        factor = Decimal(100 - self.discount_percent) / Decimal(100)
        return (self.price * factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def clean(self):
        super().clean()
        if self.discount_starts_at and self.discount_ends_at and self.discount_ends_at <= self.discount_starts_at:
            raise ValidationError({'discount_ends_at': 'Кінець знижки має бути пізніше за її початок.'})

    def __str__(self):
        return self.name


class GameSubmission(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Очікує розгляду'
        APPROVED = 'approved', 'Схвалено'
        REJECTED = 'rejected', 'Відхилено'

    submitter_name = models.CharField('Ваше ім’я', max_length=100)
    submitter_telegram = models.CharField('Ваш Telegram нік', max_length=100, help_text='Наприклад, @username')
    submitter_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='game_submissions',
    )
    published_game = models.OneToOneField(
        'games',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_submission',
    )
    kind = models.CharField('Тип пропозиції', max_length=12, choices=CatalogType.choices, default=CatalogType.GAME)
    name = models.CharField('Назва пропозиції', max_length=100)
    description = models.CharField('Опис', max_length=255)
    release_date = models.DateField('Дата виходу або запуску', blank=True, null=True)
    developer = models.CharField('Розробник, автор або команда', max_length=100, blank=True)
    genre = models.CharField('Жанр', max_length=80, blank=True)
    system_requirements = models.TextField('Системні вимоги', blank=True)
    photo = models.ImageField(upload_to='submissions/covers/', blank=True, null=True)
    link = models.URLField('Посилання на гру', blank=True)
    price = models.DecimalField('Ціна', max_digits=10, decimal_places=2, blank=True, null=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    submitted_at = models.DateTimeField('Надіслано', auto_now_add=True)

    class Meta:
        ordering = ('-submitted_at',)
        verbose_name = 'заявка на гру'
        verbose_name_plural = 'заявки на ігри'

    def __str__(self):
        return f'{self.name} — {self.get_status_display()}'

# Create your models here.


class TelegramProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='telegram_profile',
    )
    telegram_username = models.CharField(max_length=32, unique=True)

    def __str__(self):
        return f'@{self.telegram_username} ({self.user})'


class GamePurchase(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Очікує оплати'
        PAID = 'paid', 'Оплачено'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='game_purchases')
    game = models.ForeignKey(games, on_delete=models.PROTECT, related_name='purchases')
    order_reference = models.CharField(max_length=64, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    telegram_notified_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ('-paid_at', '-created_at')

    def __str__(self):
        return f'{self.user} — {self.game} ({self.status})'


class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='game_favorites')
    game = models.ForeignKey(games, on_delete=models.CASCADE, related_name='favorites')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('user', 'game'), name='unique_game_favorite')]
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.user} — {self.game}'


class GameReview(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='game_reviews')
    game = models.ForeignKey(games, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField(max_length=2000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('user', 'game'), name='unique_review_per_user_game'),
        ]
        ordering = ('-updated_at',)

    def __str__(self):
        return f'{self.user} — {self.game}: {self.rating}/5'


class GameScreenshot(models.Model):
    game = models.ForeignKey(games, on_delete=models.CASCADE, related_name='screenshots')
    image = models.ImageField(upload_to='games/screenshots/')
    caption = models.CharField(max_length=120, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ('position', 'pk')

    def __str__(self):
        return self.caption or f'{self.game} screenshot'


class SiteNotification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='site_notifications')
    submission = models.ForeignKey(
        GameSubmission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
    )
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.user}: {self.message}'
