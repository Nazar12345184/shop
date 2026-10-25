from django import forms

from .models import GameSubmission


class GameSubmissionForm(forms.ModelForm):
    class Meta:
        model = GameSubmission
        fields = (
            'submitter_name',
            'submitter_telegram',
            'name',
            'description',
            'release_date',
            'developer',
            'photo',
            'price',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'release_date': forms.DateInput(attrs={'type': 'date'}),
            'photo': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
            'price': forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
        }
