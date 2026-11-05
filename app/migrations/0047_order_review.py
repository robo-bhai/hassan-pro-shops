import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0046_rider_system'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderReview',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vendor_rating', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('vendor_comment', models.CharField(blank=True, default='', max_length=300)),
                ('rider_rating', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('rider_comment', models.CharField(blank=True, default='', max_length=300)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('rider', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviews', to='app.riderprofile')),
                ('sale_order', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='review', to='app.saleorder')),
                ('vendor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviews', to='app.vendor')),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
