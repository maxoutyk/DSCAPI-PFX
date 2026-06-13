# Generated manually for PublicSignArtifact

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_portalsignartifact'),
    ]

    operations = [
        migrations.CreateModel(
            name='PublicSignArtifact',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('session_key', models.CharField(db_index=True, max_length=64)),
                ('encrypted_pdf', models.BinaryField()),
                ('filename', models.CharField(max_length=255)),
                ('signer_name', models.CharField(blank=True, max_length=120)),
                ('expires_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
