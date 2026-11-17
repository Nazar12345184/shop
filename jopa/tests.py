import json
import uuid
import zipfile
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.test import override_settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from .models import GamePurchase, GameSubmission, games


class HomeViewTests(TestCase):
    def test_home_renders_index_template(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'index.html')

    def test_header_has_admin_link_only_for_staff(self):
        regular = get_user_model().objects.create_user(username='regular', password='test-password')
        admin = get_user_model().objects.create_superuser(
            username='admin',
            password='test-password',
            email='admin@example.com',
        )

        self.client.force_login(regular)
        regular_response = self.client.get('/')
        self.assertContains(regular_response, 'Бібліотека')
        self.assertContains(regular_response, 'Запропонувати')
        self.assertNotContains(regular_response, 'Керування')

        self.client.force_login(admin)
        admin_response = self.client.get('/')
        self.assertContains(admin_response, 'Керування')


class AuthorAndProfileTests(TestCase):
    def setUp(self):
        self.author = get_user_model().objects.create_user(
            username='creator',
            password='test-password',
            first_name='Іван',
            last_name='Тест',
        )
        self.game = games.objects.create(
            name='Author game',
            description='A test project',
            author=self.author,
        )

    def test_author_can_download_without_purchase(self):
        self.game.download_file.save(
            'author-game.zip',
            SimpleUploadedFile('author-game.zip', b'author game archive'),
        )
        self.client.force_login(self.author)

        catalog = self.client.get(reverse('home'))
        detail = self.client.get(reverse('game_detail', args=(self.game.pk,)))
        download = self.client.get(reverse('download_game_file', args=(self.game.pk,)))

        download_url = reverse('download_game_file', args=(self.game.pk,))
        self.assertContains(catalog, download_url)
        self.assertContains(detail, download_url)
        self.assertEqual(download.status_code, 200)
        self.assertFalse(GamePurchase.objects.filter(user=self.author, game=self.game).exists())

    def test_author_list_and_detail_render(self):
        list_response = self.client.get(reverse('author_list'))
        detail_response = self.client.get(reverse('author_detail', args=(self.author.pk,)))

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, 'Іван Тест')
        self.assertTemplateUsed(list_response, 'authors.html')
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'Author game')

    def test_profile_shows_only_completed_purchases(self):
        pending = GamePurchase.objects.create(
            user=self.author,
            game=self.game,
            order_reference='pending-profile-order',
            amount='10.00',
            status=GamePurchase.Status.PENDING,
        )
        paid = GamePurchase.objects.create(
            user=self.author,
            game=self.game,
            order_reference='paid-profile-order',
            amount='10.00',
            status=GamePurchase.Status.PAID,
        )
        self.client.force_login(self.author)

        response = self.client.get(reverse('profile'))

        self.assertEqual(list(response.context['purchases']), [paid])
        self.assertNotContains(response, 'pending-profile-order')

    def test_profile_updates_user_and_telegram_data(self):
        self.client.force_login(self.author)

        response = self.client.post(reverse('profile'), {
            'first_name': 'Новий',
            'last_name': 'Автор',
            'email': 'author@example.com',
            'telegram_username': '@new_creator',
        })

        self.assertRedirects(response, reverse('profile'))
        self.author.refresh_from_db()
        self.assertEqual(self.author.first_name, 'Новий')
        self.assertEqual(self.author.last_name, 'Автор')
        self.assertEqual(self.author.email, 'author@example.com')
        self.assertEqual(self.author.telegram_profile.telegram_username, 'new_creator')


class PurchasedGameViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='buyer', password='test-password')
        self.game = games.objects.create(name='Test game', description='A short description', price=0)

    def test_library_navigation_opens_authors(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('library'))

        self.assertContains(response, reverse('author_list'))
        self.assertContains(response, '>Автори<', html=False)

    def test_free_purchase_redirects_to_purchased_game_page(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('buy_game', args=(self.game.pk,)))

        self.assertRedirects(response, reverse('purchased_game', args=(self.game.pk,)))
        self.assertContains(self.client.get(reverse('purchased_game', args=(self.game.pk,))), 'ГРУ ДОДАНО ДО ТВОЄЇ БІБЛІОТЕКИ')

    def test_owned_game_shows_download_on_catalog_and_detail(self):
        self.game.download_file.save(
            'owned-game.zip',
            SimpleUploadedFile('owned-game.zip', b'game archive'),
        )
        GamePurchase.objects.create(
            user=self.user,
            game=self.game,
            order_reference='owned-direct-download',
            amount='0.00',
            status=GamePurchase.Status.PAID,
        )
        self.client.force_login(self.user)

        catalog = self.client.get(reverse('home'))
        detail = self.client.get(reverse('game_detail', args=(self.game.pk,)))

        download_url = reverse('download_game_file', args=(self.game.pk,))
        self.assertContains(catalog, download_url)
        self.assertContains(detail, download_url)

    def test_pending_payment_return_shows_refreshable_status(self):
        purchase = GamePurchase.objects.create(
            user=self.user,
            game=self.game,
            order_reference='pending-test-order',
            amount='10.00',
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('purchased_game', args=(self.game.pk,)),
            {'order_reference': purchase.order_reference},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ОПЛАТА ПЕРЕВІРЯЄТЬСЯ')

    def test_unowned_game_page_is_not_accessible(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('purchased_game', args=(self.game.pk,)))

        self.assertEqual(response.status_code, 404)

    @override_settings(
        SITE_URL='https://shop.example',
        WAYFORPAY_MERCHANT_ACCOUNT='merchant',
        WAYFORPAY_SECRET_KEY='test-secret',
        WAYFORPAY_MERCHANT_DOMAIN='shop.example',
    )
    @patch('jopa.views.urlopen')
    def test_paid_purchase_returns_to_owned_game_page(self, mock_urlopen):
        self.game.price = '10.00'
        self.game.save(update_fields=('price',))
        gateway_response = MagicMock()
        gateway_response.__enter__.return_value.read.return_value = json.dumps({
            'invoiceUrl': 'https://pay.example/invoice',
        }).encode()
        mock_urlopen.return_value = gateway_response
        self.client.force_login(self.user)

        response = self.client.post(reverse('buy_game', args=(self.game.pk,)))

        self.assertRedirects(response, 'https://pay.example/invoice', fetch_redirect_response=False)
        purchase = GamePurchase.objects.get(user=self.user, game=self.game)
        payload = json.loads(mock_urlopen.call_args.args[0].data)
        self.assertEqual(
            payload['returnUrl'],
            f'https://shop.example{reverse("purchased_game", args=(self.game.pk,))}?order_reference={purchase.order_reference}',
        )


class GameSubmissionUploadTests(TestCase):
    def submission_data(self):
        return {
            'submitter_name': 'Game creator',
            'submitter_telegram': '@tester_123',
            'kind': 'game',
            'name': 'Uploaded game',
            'description': 'A game with an upload',
        }

    def test_submission_accepts_a_game_file(self):
        data = self.submission_data()
        data['download_file'] = SimpleUploadedFile('game.zip', b'game data')

        response = self.client.post(reverse('submit_game'), data)

        self.assertRedirects(response, reverse('submit_game'))
        submission = GameSubmission.objects.get(name='Uploaded game')
        self.assertTrue(submission.download_file.name.startswith('submissions/files/'))

    def test_anonymous_submission_accepts_a_folder_upload(self):
        upload_id = str(uuid.uuid4())
        response = self.client.post(reverse('upload_game_folder_chunk'), {
            'upload_id': upload_id,
            'file_index': '0',
            'chunk_index': '0',
            'chunk_count': '1',
            'chunk': SimpleUploadedFile('chunk.bin', b'game data'),
        })
        self.assertEqual(response.status_code, 200)

        data = self.submission_data()
        data['folder_upload_id'] = upload_id
        data['folder_upload_manifest'] = json.dumps([{'path': 'game/readme.txt', 'chunks': 1}])
        response = self.client.post(reverse('submit_game'), data)

        self.assertRedirects(response, reverse('submit_game'))
        submission = GameSubmission.objects.get(name='Uploaded game')
        with submission.download_file.open('rb') as uploaded_file:
            with zipfile.ZipFile(BytesIO(uploaded_file.read())) as archive:
                self.assertEqual(archive.read('game/readme.txt'), b'game data')

    def test_submission_rejects_both_file_and_folder(self):
        data = self.submission_data()
        data['download_file'] = SimpleUploadedFile('game.zip', b'game data')
        data['folder_upload_id'] = str(uuid.uuid4())

        response = self.client.post(reverse('submit_game'), data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(GameSubmission.objects.exists())
