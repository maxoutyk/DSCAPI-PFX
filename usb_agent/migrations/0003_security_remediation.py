from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usb_agent', '0002_usbsignjob_api_key_nullable_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='usbsignjob',
            name='sign_token',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AlterField(
            model_name='agentpairingcode',
            name='code',
            field=models.CharField(db_index=True, max_length=64),
        ),
    ]
