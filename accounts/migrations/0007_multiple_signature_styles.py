from django.db import migrations, models
import django.db.models.deletion


def seed_style_names(apps, schema_editor):
    TenantSignatureStyle = apps.get_model('accounts', 'TenantSignatureStyle')
    for style in TenantSignatureStyle.objects.all():
        style.name = 'Default'
        style.is_default = True
        style.save(update_fields=['name', 'is_default'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_publicsignartifact'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenantsignaturestyle',
            name='name',
            field=models.CharField(default='Default', max_length=80),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='tenantsignaturestyle',
            name='is_default',
            field=models.BooleanField(
                default=False,
                help_text='Used for API signing when signature_style is omitted.',
            ),
        ),
        migrations.RunPython(seed_style_names, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='tenantsignaturestyle',
            name='is_enabled',
            field=models.BooleanField(
                default=False,
                help_text='When off, this style is ignored unless selected explicitly by name.',
            ),
        ),
        migrations.AlterField(
            model_name='tenantsignaturestyle',
            name='tenant',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='signature_styles',
                to='accounts.tenant',
            ),
        ),
        migrations.AlterModelOptions(
            name='tenantsignaturestyle',
            options={
                'ordering': ['name'],
                'verbose_name': 'Tenant signature style',
                'verbose_name_plural': 'Tenant signature styles',
            },
        ),
        migrations.AddConstraint(
            model_name='tenantsignaturestyle',
            constraint=models.UniqueConstraint(
                fields=('tenant', 'name'),
                name='uniq_tenant_signature_style_name',
            ),
        ),
        migrations.AddConstraint(
            model_name='tenantsignaturestyle',
            constraint=models.UniqueConstraint(
                condition=models.Q(('is_default', True)),
                fields=('tenant',),
                name='uniq_tenant_default_signature_style',
            ),
        ),
    ]
