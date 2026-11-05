# Step 4.2: remember how much of each sale line came out of which batch.
# Old sales: only lines that used exactly ONE batch can be copied safely (the whole qty came
# from that batch). Lines that used 2+ batches stay without rows = "unknown split".
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


def backfill_single_batch(apps, schema_editor):
    SaleItem = apps.get_model('app', 'SaleItem')
    Usage = apps.get_model('app', 'SaleItemBatchUsage')
    rows = []
    for item in SaleItem.objects.prefetch_related('batches_used').iterator(chunk_size=500):
        batches = list(item.batches_used.all())
        if len(batches) == 1:
            rows.append(Usage(sale_item_id=item.pk, batch_id=batches[0].pk,
                              qty=item.qty, cost_price=batches[0].price or Decimal('0.00')))
        if len(rows) >= 500:
            Usage.objects.bulk_create(rows)
            rows = []
    if rows:
        Usage.objects.bulk_create(rows)


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0036_category_min_margin'),
    ]

    operations = [
        migrations.CreateModel(
            name='SaleItemBatchUsage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('qty', models.FloatField()),
                ('cost_price', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10)),
                ('batch', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sale_usages', to='app.stockbatch')),
                ('sale_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='batch_usages', to='app.saleitem')),
            ],
            options={
                'verbose_name_plural': '5.2. Sale Item Batch Usage',
                'indexes': [models.Index(fields=['batch'], name='saleusage_batch_idx')],
            },
        ),
        migrations.RunPython(backfill_single_batch, migrations.RunPython.noop),
    ]
