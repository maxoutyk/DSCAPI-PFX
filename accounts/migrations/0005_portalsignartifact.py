import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_tenant_signature_style'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PortalSignArtifact',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('encrypted_pdf', models.BinaryField()),
                ('filename', models.CharField(max_length=255)),
                ('signing_event_id', models.PositiveIntegerField(blank=True, null=True)),
                ('hash_before_prefix', models.CharField(blank=True, max_length=8)),
                ('hash_after_prefix', models.CharField(blank=True, max_length=8)),
                ('document_type_label', models.CharField(blank=True, max_length=64)),
                ('expires_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='portal_sign_artifacts', to='accounts.tenant')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='portal_sign_artifacts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
