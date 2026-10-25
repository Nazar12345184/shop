from django import forms
from django.contrib.auth.forms import UserCreationForm
import re

from .models import CatalogType, GameSubmission, TelegramProfile


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
            'photo',
            'link',
            'price',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'release_date': forms.DateInput(attrs={'type': 'date'}),
            'photo': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
            'price': forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
        }
