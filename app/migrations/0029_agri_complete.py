# Agri Edition (complete): GRN batch/expiry, product agri details, expiry write-off records
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0028_agri_edition'),
    ]

    operations = [
        migrations.AddField(model_name='goodsreceiveditem', name='batch_no',
                            field=models.CharField(blank=True, max_length=50, null=True)),
        migrations.AddField(model_name='goodsreceiveditem', name='expiry_date',
                            field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name='product', name='active_ingredient',
                            field=models.CharField(blank=True, help_text='e.g. Imidacloprid 20% SL, or NPK 18-46-0', max_length=150, null=True)),
        migrations.AddField(model_name='product', name='registration_no',
                            field=models.CharField(blank=True, help_text='DPP / department registration number', max_length=60, null=True)),
        migrations.AddField(model_name='product', name='pack_size',
                            field=models.CharField(blank=True, help_text='e.g. 50 kg bag, 250 ml bottle', max_length=40, null=True)),
        migrations.AddField(model_name='product', name='target_crops',
                            field=models.CharField(blank=True, help_text='Crops it is used on', max_length=150, null=True)),
        migrations.CreateModel(
            name='ExpiryWriteOff',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('batch_no', models.CharField(blank=True, max_length=50, null=True)),
                ('expiry_date', models.DateField(blank=True, null=True)),
                ('qty', models.FloatField()),
                ('unit_cost', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=15)),
                ('value', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=15)),
                ('reason', models.CharField(choices=[('expired', 'Expired'), ('damaged', 'Damaged / spoiled'), ('vendor_return', 'Sent back to supplier')], default='expired', max_length=20)),
                ('note', models.CharField(blank=True, default='', max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('batch', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='app.stockbatch')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='agri_writeoffs', to='app.product')),
                ('warehouse', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='agri_writeoffs', to='app.warehouse')),
            ],
            options={'verbose_name_plural': 'Agri: Expiry write-offs', 'ordering': ['-created_at', '-id']},
        ),
    ]
