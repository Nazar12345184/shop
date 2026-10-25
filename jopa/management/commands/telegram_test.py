from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from jopa.views import send_telegram_notification


class Command(BaseCommand):
    help = 'Send a test message using the configured Telegram bot.'

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
            raise CommandError('TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is empty in the server environment.')

        try:
            send_telegram_notification('Тест: Telegram-сповіщення сайту налаштовано.')
        except Exception as exc:
            detail = str(exc).replace(settings.TELEGRAM_BOT_TOKEN, '[приховано]')
            raise CommandError(f'Не вдалося надіслати тестове повідомлення: {detail}') from exc

        self.stdout.write(self.style.SUCCESS('Тестове повідомлення надіслано в Telegram.'))
