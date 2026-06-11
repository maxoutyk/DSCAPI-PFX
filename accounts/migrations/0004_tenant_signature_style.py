from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_signing_audit_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='TenantSignatureStyle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_enabled', models.BooleanField(
                    default=False,
                    help_text='When off, global platform defaults are used (existing API behaviour).',
                )),
                ('anchor_text', models.CharField(
                    blank=True,
                    help_text='Text to search for in the PDF (e.g. Authorised Signatory). Leave blank to use platform default.',
                    max_length=120,
                )),
                ('font_size', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('box_min_width', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('box_height', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('box_right_padding', models.SmallIntegerField(blank=True, null=True)),
                ('box_shift_right', models.SmallIntegerField(blank=True, null=True)),
                ('box_gap_above_label', models.SmallIntegerField(blank=True, null=True)),
                ('box_shift_down_fitz', models.SmallIntegerField(blank=True, null=True)),
                ('box_page_margin', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('icon_display_width', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('icon_overlap_inset', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('icon_padding', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('custom_icon', models.ImageField(blank=True, null=True, upload_to='signature_icons/%Y/%m/')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='signature_style',
                    to='accounts.tenant',
                )),
            ],
            options={
                'verbose_name': 'Tenant signature style',
            },
        ),
    ]
