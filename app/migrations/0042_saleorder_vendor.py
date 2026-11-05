from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0041_vendor_store'),
    ]

    operations = [
        migrations.AddField(model_name='saleorder', name='vendor',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='portal_sale_orders', to='app.vendor', verbose_name='Store (Vendor)',
                help_text='Khali = shop ka apna order. Bhara = is store ke dashboard par dikhega.')),
        migrations.AddField(model_name='saleorder', name='delivery_fee',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10)),
        migrations.AddField(model_name='saleorder', name='payment_method',
            field=models.CharField(blank=True, default='', max_length=20)),
        migrations.AddField(model_name='saleorder', name='prep_minutes',
            field=models.PositiveSmallIntegerField(blank=True, null=True,
                help_text='Vendor accept karte waqt batata hai: tayyar hone mein kitne minute')),
        migrations.AddField(model_name='saleorder', name='reject_reason',
            field=models.CharField(blank=True, default='', max_length=200)),
        migrations.AddField(model_name='saleorder', name='vendor_responded_at',
            field=models.DateTimeField(blank=True, null=True)),
        migrations.AddIndex(model_name='saleorder',
            index=models.Index(fields=['vendor', 'status'], name='app_saleord_vendor__idx')),
    ]
