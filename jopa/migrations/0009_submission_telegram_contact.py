from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jopa', '0008_gamesubmission'),
    ]

    operations = [
        migrations.RenameField(
            model_name='gamesubmission',
            old_name='submitter_email',
            new_name='submitter_telegram',
        ),
        migrations.AlterField(
            model_name='gamesubmission',
            name='submitter_telegram',
            field=models.CharField(
                help_text='Наприклад, @username',
                max_length=100,
                verbose_name='Ваш Telegram нік',
            ),
        ),
    ]
