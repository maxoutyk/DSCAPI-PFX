import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_quota_plans_and_entitlements'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TenantInvite',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', models.EmailField(db_index=True, max_length=254)),
                (
                    'role',
                    models.CharField(
                        choices=[('owner', 'Owner'), ('member', 'Member')],
                        default='member',
                        max_length=20,
                    ),
                ),
                ('token', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('accepted_at', models.DateTimeField(blank=True, null=True)),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                (
                    'invited_by',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='sent_tenant_invites',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'tenant',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='invites',
                        to='accounts.tenant',
                    ),
                ),
            ],
            options={
                'indexes': [models.Index(fields=['tenant', 'email'], name='accounts_te_tenant__a0f2c1_idx')],
            },
        ),
    ]
