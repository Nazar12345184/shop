import json
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.test import override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import GamePurchase, games


class HomeViewTests(TestCase):
    def test_home_renders_index_template(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'index.html')


class PurchasedGameViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='buyer', password='test-password')
        self.game = games.objects.create(name='Test game', description='A short description', price=0)

    def test_free_purchase_redirects_to_purchased_game_page(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('buy_game', args=(self.game.pk,)))

        self.assertRedirects(response, reverse('purchased_game', args=(self.game.pk,)))
        self.assertContains(self.client.get(reverse('purchased_game', args=(self.game.pk,))), 'ГРУ ДОДАНО ДО ТВОЄЇ БІБЛІОТЕКИ')

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
