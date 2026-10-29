import json
from pathlib import Path

from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.admin.sites import NotRegistered
from .models import Favorite, GamePurchase, GameReview, GameScreenshot, GameSubmission, SiteNotification, TelegramProfile, games


User = get_user_model()
try:
    admin.site.unregister(User)
except NotRegistered:
    pass


@admin.register(User)
class SiteUserAdmin(DjangoUserAdmin):
    list_display = ('username', 'email', 'is_active', 'is_staff', 'is_superuser', 'last_login')
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'groups')
    search_fields = ('username', 'email', 'first_name', 'last_name')

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
            return fieldsets
        return tuple(fieldset for fieldset in fieldsets if fieldset[0] != 'Permissions')


def write_game_json(game):
    output_dir = Path(settings.BASE_DIR) / 'generated' / 'games'
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        'id': game.pk,
        'kind': game.kind,
        'name': game.name,
        'description': game.description,
        'release_date': game.release_date.isoformat() if game.release_date else None,
        'developer': game.developer,
        'genre': game.genre,
        'system_requirements': game.system_requirements,
        'contact_telegram': game.contact_telegram,
        'author': game.author.username if game.author_id else '',
        'photo': game.photo.name if game.photo else '',
        'link': game.link,
        'price': str(game.price) if game.price is not None else None,
        'discount_percent': game.discount_percent,
        'current_price': str(game.current_price) if game.current_price is not None else None,
        'discount_starts_at': game.discount_starts_at.isoformat() if game.discount_starts_at else None,
        'discount_ends_at': game.discount_ends_at.isoformat() if game.discount_ends_at else None,
    }
    (output_dir / f'game-{game.pk}.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


class GameScreenshotInline(admin.TabularInline):
    model = GameScreenshot
    extra = 1


@admin.register(games)
class GamesAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'genre', 'developer', 'release_date', 'price', 'discount_percent')
    search_fields = ('name', 'developer', 'genre')
    list_filter = ('kind', 'genre')
    ordering = ('name',)
    inlines = (GameScreenshotInline,)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        write_game_json(obj)


@admin.register(GameSubmission)
class GameSubmissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'developer', 'submitter_name', 'submitter_telegram', 'submitted_at', 'status')
    list_filter = ('kind', 'status')
    search_fields = ('name', 'developer', 'submitter_name', 'submitter_telegram')
    readonly_fields = ('status', 'submitted_at')
    actions = ('approve_submissions', 'reject_submissions')

    def has_add_permission(self, request):
        return False

    @admin.action(description='Схвалити вибрані заявки')
    def approve_submissions(self, request, queryset):
        approved = 0
        for submission in queryset.filter(status=GameSubmission.Status.PENDING):
            game = games.objects.create(
                name=submission.name,
                kind=submission.kind,
                description=submission.description,
                release_date=submission.release_date,
                developer=submission.developer,
                genre=submission.genre,
                system_requirements=submission.system_requirements,
                contact_telegram=submission.submitter_telegram,
                author=submission.submitter_user,
                photo=submission.photo.name if submission.photo else None,
                link=submission.link,
                price=submission.price,
            )
            write_game_json(game)
            submission.status = GameSubmission.Status.APPROVED
            submission.published_game = game
            submission.save(update_fields=('status', 'published_game'))
            if submission.submitter_user_id:
                SiteNotification.objects.create(
                    user=submission.submitter_user,
                    submission=submission,
                    message=f'Заявку «{submission.name}» схвалено та опубліковано.',
                )
            approved += 1
        self.message_user(request, f'Схвалено заявок: {approved}. Ігри додано до каталогу.', messages.SUCCESS)

    @admin.action(description='Відхилити вибрані заявки')
    def reject_submissions(self, request, queryset):
        rejected = 0
        for submission in queryset.filter(status=GameSubmission.Status.PENDING):
            submission.status = GameSubmission.Status.REJECTED
            submission.save(update_fields=('status',))
            if submission.submitter_user_id:
                SiteNotification.objects.create(
                    user=submission.submitter_user,
                    submission=submission,
                    message=f'Заявку «{submission.name}» відхилено. Можеш подати іншу пропозицію.',
                )
            rejected += 1
        self.message_user(request, f'Відхилено заявок: {rejected}.', messages.INFO)

# Register your models here.


@admin.register(TelegramProfile)
class TelegramProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'telegram_username')
    search_fields = ('user__username', 'telegram_username')


@admin.register(GamePurchase)
class GamePurchaseAdmin(admin.ModelAdmin):
    list_display = ('user', 'game', 'amount', 'status', 'created_at', 'paid_at')
    list_filter = ('status',)
    search_fields = ('user__username', 'game__name', 'order_reference')
    readonly_fields = ('user', 'game', 'order_reference', 'amount', 'status', 'created_at', 'paid_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GameReview)
class GameReviewAdmin(admin.ModelAdmin):
    list_display = ('game', 'user', 'rating', 'updated_at')
    list_filter = ('rating',)
    search_fields = ('game__name', 'user__username', 'text')
    readonly_fields = ('user', 'game', 'created_at', 'updated_at')


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'game', 'created_at')
    search_fields = ('user__username', 'game__name')
    readonly_fields = ('user', 'game', 'created_at')
