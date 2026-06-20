from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_companyprofile_nic_portal_credentials'),
    ]

    operations = [
        migrations.AddField(
            model_name='apikey',
            name='customer_label',
            field=models.CharField(
                blank=True,
                help_text='Optional customer or integration name for usage reports.',
                max_length=120,
            ),
        ),
    ]
