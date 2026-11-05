from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0040_vendor_commission'),
    ]

    operations = [
        migrations.AddField(model_name='vendorprofile', name='store_description',
            field=models.TextField(blank=True, default='', max_length=1000)),
        migrations.AddField(model_name='vendorprofile', name='logo',
            field=models.ImageField(blank=True, null=True, upload_to='vendor_stores/logos/')),
        migrations.AddField(model_name='vendorprofile', name='cover_image',
            field=models.ImageField(blank=True, null=True, upload_to='vendor_stores/covers/')),
        migrations.AddField(model_name='vendorprofile', name='store_status',
            field=models.CharField(choices=[('open', 'Open'), ('busy', 'Busy'), ('closed', 'Closed')], default='open',
                help_text='Closed = customer is store se order nahi de sakta. Busy = order milte hain, par der ho sakti ha.',
                max_length=6)),
        migrations.AddField(model_name='vendorprofile', name='opens_at',
            field=models.TimeField(blank=True, null=True, help_text='Khali = hamesha khula (status ke mutabiq)')),
        migrations.AddField(model_name='vendorprofile', name='closes_at',
            field=models.TimeField(blank=True, null=True)),
        migrations.AddField(model_name='vendorprofile', name='min_order_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10)),
        migrations.AddField(model_name='vendorprofile', name='delivery_fee',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8)),
        migrations.AddField(model_name='vendorprofile', name='delivery_time_min',
            field=models.PositiveSmallIntegerField(default=30, help_text='Minutes')),
        migrations.AddField(model_name='vendorprofile', name='delivery_time_max',
            field=models.PositiveSmallIntegerField(default=45, help_text='Minutes')),
    ]
