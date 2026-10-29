import json
from pathlib import Path

from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from .models import Favorite, GamePurchase, GameReview, GameScreenshot, GameSubmission, TelegramProfile, games


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
        'photo': game.photo.name if game.photo else '',
        'link': game.link,
        'price': str(game.price) if game.price is not None else None,
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
    list_display = ('name', 'kind', 'genre', 'developer', 'release_date', 'price')
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
                photo=submission.photo.name if submission.photo else None,
                link=submission.link,
                price=submission.price,
            )
            write_game_json(game)
            submission.status = GameSubmission.Status.APPROVED
            submission.save(update_fields=('status',))
            approved += 1
        self.message_user(request, f'Схвалено заявок: {approved}. Ігри додано до каталогу.', messages.SUCCESS)

    @admin.action(description='Відхилити вибрані заявки')
    def reject_submissions(self, request, queryset):
        rejected = queryset.filter(status=GameSubmission.Status.PENDING).update(
            status=GameSubmission.Status.REJECTED
        )
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
