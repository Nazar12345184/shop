from django.db import models
from django.conf import settings


class games(models.Model):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255)
    release_date = models.DateField()
    developer = models.CharField(max_length=100)
    photo = models.ImageField(upload_to='static/img/', blank=True, null=True)
    link = models.URLField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    def __str__(self):
        return self.name


class GameSubmission(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Очікує розгляду'
        APPROVED = 'approved', 'Схвалено'
        REJECTED = 'rejected', 'Відхилено'

    submitter_name = models.CharField('Ваше ім’я', max_length=100)
    submitter_telegram = models.CharField('Ваш Telegram нік', max_length=100, help_text='Наприклад, @username')
    name = models.CharField('Назва гри', max_length=100)
    description = models.CharField('Опис', max_length=255)
    release_date = models.DateField('Дата виходу')
    developer = models.CharField('Розробник', max_length=100)
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

    class Meta:
        ordering = ('-paid_at', '-created_at')

    def __str__(self):
        return f'{self.user} — {self.game} ({self.status})'
