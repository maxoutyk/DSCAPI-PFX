import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_password_reset_token'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='usagelog',
            name='api_key',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='usage_logs',
                to='accounts.apikey',
            ),
        ),
        migrations.AddField(
            model_name='usagelog',
            name='client_ip',
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='usagelog',
            name='detected_keyword',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='usagelog',
            name='detection_confidence',
            field=models.CharField(
                choices=[('high', 'High'), ('low', 'Low'), ('none', 'None')],
                default='none',
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name='usagelog',
            name='document_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('tax_invoice', 'Tax Invoice'),
                    ('purchase_order', 'Purchase Order'),
                    ('delivery_challan', 'Delivery Challan'),
                    ('credit_note', 'Credit Note'),
                    ('debit_note', 'Debit Note'),
                    ('proforma_invoice', 'Proforma Invoice'),
                    ('quotation', 'Quotation'),
                    ('unknown', 'Unknown'),
                ],
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='usagelog',
            name='hash_after',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name='usagelog',
            name='hash_before',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name='usagelog',
            name='user',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='signing_events',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterModelOptions(
            name='usagelog',
            options={
                'ordering': ['-created_at'],
                'verbose_name': 'Signing event',
                'verbose_name_plural': 'Signing events',
            },
        ),
    ]
