from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0014_rename_accounts_te_tenant__a0f2c1_idx_accounts_te_tenant__11dded_idx'),
    ]

    operations = [
        migrations.AddField(
            model_name='quotaentitlement',
            name='expiry_reminder_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='quotaentitlement',
            name='low_quota_notified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
