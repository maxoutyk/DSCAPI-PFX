from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_usagelog_client_context'),
    ]

    operations = [
        migrations.AddField(
            model_name='companyprofile',
            name='nic_portal_username',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='companyprofile',
            name='encrypted_nic_portal_password',
            field=models.BinaryField(blank=True, null=True),
        ),
    ]
