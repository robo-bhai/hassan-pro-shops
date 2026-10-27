from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0020_storecount_storecountline_storeissuerequest_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Translation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=300, unique=True)),
                ('source', models.CharField(max_length=300)),
                ('ur', models.TextField(blank=True, default='')),
                ('ar', models.TextField(blank=True, default='')),
                ('ur_status', models.CharField(blank=True, choices=[('', 'Missing'), ('default', 'Default'), ('auto', 'Auto'), ('manual', 'Manual'), ('reviewed', 'Reviewed')], default='', max_length=10)),
                ('ar_status', models.CharField(blank=True, choices=[('', 'Missing'), ('default', 'Default'), ('auto', 'Auto'), ('manual', 'Manual'), ('reviewed', 'Reviewed')], default='', max_length=10)),
                ('seen_count', models.PositiveIntegerField(default=0)),
                ('last_seen', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['source'],
            },
        ),
    ]
