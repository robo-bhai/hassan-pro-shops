# Price history / audit log (Step 1 of the pricing upgrade). Adds one new table, touches nothing else.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0034_remove_stores_module'),
    ]

    operations = [
        migrations.CreateModel(
            name='PriceChangeLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('changed_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('price_field', models.CharField(choices=[('batch_selling_price', 'Batch selling price'), ('product_price', 'Product price'), ('product_discount', 'Product discount %')], db_index=True, default='batch_selling_price', max_length=30)),
                ('source', models.CharField(choices=[('single', 'Single edit'), ('bulk', 'Bulk apply'), ('undo', 'Undo'), ('approval', 'Approved request'), ('system', 'System')], db_index=True, default='single', max_length=12)),
                ('product_name', models.CharField(blank=True, default='', max_length=100)),
                ('batch_ref', models.CharField(blank=True, default='', max_length=40)),
                ('old_value', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('new_value', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('cost_price', models.DecimalField(blank=True, decimal_places=2, help_text='Batch cost at the time of the change', max_digits=12, null=True)),
                ('run_id', models.UUIDField(blank=True, db_index=True, help_text='Same id for every row of one bulk apply', null=True)),
                ('rule', models.JSONField(blank=True, help_text='Bulk rule used: mode / value / rounding', null=True)),
                ('reason', models.CharField(blank=True, default='', max_length=255)),
                ('changed_by_name', models.CharField(blank=True, default='', max_length=150)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('batch', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='price_logs', to='app.stockbatch')),
                ('changed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='price_changes', to=settings.AUTH_USER_MODEL)),
                ('product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='price_logs', to='app.product')),
            ],
            options={
                'verbose_name': 'Price change',
                'verbose_name_plural': 'Price history',
                'ordering': ['-changed_at', '-id'],
                'indexes': [
                    models.Index(fields=['product', '-changed_at'], name='app_pricech_product_6d1f0a_idx'),
                    models.Index(fields=['batch', '-changed_at'], name='app_pricech_batch_i_3b7c2e_idx'),
                ],
            },
        ),
    ]
