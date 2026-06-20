from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_tenant_gst_monthly_quota_tenant_gst_usage_this_month_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='usagelog',
            name='user_agent',
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
        migrations.AddField(
            model_name='usagelog',
            name='client_mac',
            field=models.CharField(blank=True, max_length=17, null=True),
        ),
    ]
