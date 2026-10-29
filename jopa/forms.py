from django import forms
from django.contrib.auth.forms import UserCreationForm
import re

from django.contrib.auth import get_user_model

from .models import CatalogType, GameReview, GameSubmission, TelegramProfile, games


class RegistrationForm(UserCreationForm):
    telegram_username = forms.CharField(
        label='Telegram-нік',
        max_length=33,
        help_text='Введи свій Telegram-нік, наприклад @username.',
        widget=forms.TextInput(attrs={'placeholder': '@username', 'autocomplete': 'off'}),
    )

    class Meta(UserCreationForm.Meta):
        fields = ('username',)

    def clean_telegram_username(self):
        username = self.cleaned_data['telegram_username'].strip().lstrip('@')
        if not re.fullmatch(r'[A-Za-z0-9_]{5,32}', username):
            raise forms.ValidationError('Вкажи Telegram-нік із 5–32 латинських літер, цифр або знаків _.')
        username = username.lower()
        if TelegramProfile.objects.filter(telegram_username=username).exists():
            raise forms.ValidationError('Цей Telegram-нік уже прив’язаний до іншого акаунта.')
        return username

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            TelegramProfile.objects.create(
                user=user,
                telegram_username=self.cleaned_data['telegram_username'],
            )
        return user


class GameSubmissionForm(forms.ModelForm):
    kind = forms.ChoiceField(
        label='Що пропонуєш?',
        choices=CatalogType.choices,
        help_text='Обери категорію своєї пропозиції.',
    )

    class Meta:
        model = GameSubmission
        fields = (
            'submitter_name',
            'submitter_telegram',
            'kind',
            'name',
            'description',
            'release_date',
            'developer',
            'genre',
            'system_requirements',
            'photo',
            'link',
            'price',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'system_requirements': forms.Textarea(attrs={'rows': 4}),
            'release_date': forms.DateInput(attrs={'type': 'date'}),
            'photo': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
            'price': forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
        }

    def clean_submitter_telegram(self):
        username = self.cleaned_data['submitter_telegram'].strip().lstrip('@')
        if not re.fullmatch(r'[A-Za-z0-9_]{5,32}', username):
            raise forms.ValidationError('Вкажи Telegram нік із 5–32 латинських літер, цифр або _.')
        return f'@{username}'


class GameReviewForm(forms.ModelForm):
    class Meta:
        model = GameReview
        fields = ('rating', 'text')
        widgets = {
            'rating': forms.Select(choices=[(n, f'{n}/5') for n in range(1, 6)]),
            'text': forms.Textarea(attrs={'rows': 3, 'maxlength': 2000, 'placeholder': 'Що сподобалось або що можна покращити?'}),
        }


class ProfileForm(forms.ModelForm):
    class Meta:
        model = TelegramProfile
        fields = ('telegram_username',)
        labels = {'telegram_username': 'Telegram нік'}
        widgets = {'telegram_username': forms.TextInput(attrs={'placeholder': '@username'})}

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_telegram_username(self):
        username = self.cleaned_data['telegram_username'].strip().lstrip('@').lower()
        if not re.fullmatch(r'[A-Za-z0-9_]{5,32}', username):
            raise forms.ValidationError('Вкажи Telegram нік із 5–32 латинських літер, цифр або _.')
        if TelegramProfile.objects.filter(telegram_username=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Цей Telegram нік уже прив’язаний до іншого акаунта.')
        return username


class SiteGameAdminForm(forms.ModelForm):
    discount_starts_at = forms.DateTimeField(
        required=False,
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
    )
    discount_ends_at = forms.DateTimeField(
        required=False,
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
    )

    class Meta:
        model = games
        fields = (
            'name', 'kind', 'description', 'release_date', 'developer', 'genre',
            'system_requirements', 'contact_telegram', 'link', 'photo', 'price',
            'discount_percent', 'discount_starts_at', 'discount_ends_at',
        )
        labels = {
            'discount_starts_at': 'Початок знижки (UTC)',
            'discount_ends_at': 'Кінець знижки (UTC)',
        }
        help_texts = {
            'discount_starts_at': 'Залиш порожнім, щоб знижка діяла одразу.',
            'discount_ends_at': 'Залиш порожнім, щоб знижка не завершувалась автоматично.',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'system_requirements': forms.Textarea(attrs={'rows': 3}),
            'release_date': forms.DateInput(attrs={'type': 'date'}),
            'photo': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
            'price': forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
            'discount_percent': forms.NumberInput(attrs={'min': '0', 'max': '100', 'step': '1'}),
        }


class SiteUserAccessForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ('is_active', 'is_staff', 'is_superuser')
        labels = {
            'is_active': 'Активний',
            'is_staff': 'Доступ до адмінки',
            'is_superuser': 'Повні права',
        }
