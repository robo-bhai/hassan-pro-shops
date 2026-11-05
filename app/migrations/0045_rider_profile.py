import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0044_vendor_delivery_areas'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RiderProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('phone', models.CharField(max_length=20, unique=True)),
                ('vehicle', models.CharField(blank=True, default='', max_length=50)),
                ('is_active', models.BooleanField(default=True)),
                ('last_login_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='rider_profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': '🏍️ Riders',
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='deliveryinfo',
            name='rider',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='deliveries', to='app.riderprofile', verbose_name='Rider (login wala)'),
        ),
    ]
