from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jopa', '0011_telegramprofile_purchase_notification'),
    ]

    operations = [
        migrations.AddField(
            model_name='games',
            name='kind',
            field=models.CharField(choices=[('game', 'Гра'), ('project', 'Проєкт'), ('service', 'Послуга'), ('other', 'Інше')], default='game', max_length=12),
        ),
        migrations.AddField(
            model_name='gamesubmission',
            name='kind',
            field=models.CharField(choices=[('game', 'Гра'), ('project', 'Проєкт'), ('service', 'Послуга'), ('other', 'Інше')], default='game', max_length=12, verbose_name='Тип пропозиції'),
        ),
        migrations.AlterField(
            model_name='games',
            name='developer',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AlterField(
            model_name='games',
            name='release_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='gamesubmission',
            name='developer',
            field=models.CharField(blank=True, max_length=100, verbose_name='Розробник, автор або команда'),
        ),
        migrations.AlterField(
            model_name='gamesubmission',
            name='name',
            field=models.CharField(max_length=100, verbose_name='Назва пропозиції'),
        ),
        migrations.AlterField(
            model_name='gamesubmission',
            name='release_date',
            field=models.DateField(blank=True, null=True, verbose_name='Дата виходу або запуску'),
        ),
    ]
