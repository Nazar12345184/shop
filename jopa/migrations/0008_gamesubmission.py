from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jopa', '0007_games_link_games_price'),
    ]

    operations = [
        migrations.CreateModel(
            name='GameSubmission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('submitter_name', models.CharField(max_length=100, verbose_name='Ваше ім’я')),
                ('submitter_email', models.EmailField(max_length=254, verbose_name='Ваш Gmail')),
                ('name', models.CharField(max_length=100, verbose_name='Назва гри')),
                ('description', models.CharField(max_length=255, verbose_name='Опис')),
                ('release_date', models.DateField(verbose_name='Дата виходу')),
                ('developer', models.CharField(max_length=100, verbose_name='Розробник')),
                ('photo', models.ImageField(blank=True, null=True, upload_to='submissions/covers/')),
                ('link', models.URLField(blank=True, verbose_name='Посилання на гру')),
                ('price', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Ціна')),
                ('status', models.CharField(choices=[('pending', 'Очікує розгляду'), ('approved', 'Схвалено'), ('rejected', 'Відхилено')], default='pending', max_length=10)),
                ('submitted_at', models.DateTimeField(auto_now_add=True, verbose_name='Надіслано')),
            ],
            options={
                'verbose_name': 'заявка на гру',
                'verbose_name_plural': 'заявки на ігри',
                'ordering': ('-submitted_at',),
            },
        ),
    ]
