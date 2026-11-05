import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0045_rider_profile'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name='riderprofile', name='is_online',
            field=models.BooleanField(default=False, help_text='Rider abhi orders lene ke liye tayyar hai')),
        migrations.AddField(model_name='riderprofile', name='per_delivery_fee',
            field=models.DecimalField(decimal_places=2, default=50, max_digits=10, help_text='Har delivery par rider ki kamai (Rs.)')),
        migrations.AddField(model_name='riderprofile', name='last_seen_at',
            field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='deliveryinfo', name='rider_fee',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, help_text='Is delivery par rider ki kamai')),
        migrations.AddField(model_name='deliveryinfo', name='cash_collected',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, help_text='COD cash jo rider ne customer se liya')),
        migrations.CreateModel(
            name='RiderSettlement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('cash_in', 'Cash jama (rider se liya)'), ('payout', 'Kamai ada ki (rider ko di)')], max_length=10)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('note', models.CharField(blank=True, default='', max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('rider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='settlements', to='app.riderprofile')),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
