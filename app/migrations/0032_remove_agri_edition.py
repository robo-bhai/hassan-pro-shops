# Remove Agri Edition: drops its model (ExpiryWriteOff) and every column it added in 0028 / 0029 / 0030.
# WARNING: this deletes the data stored in those columns (batch no / expiry, farmer details,
# harvest due dates, product agri details, expiry write-off records). Take a backup before migrate.
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0031_ocr_log_alias'),
    ]

    operations = [
        migrations.DeleteModel(name='ExpiryWriteOff'),

        # 0030: store issue / transfer batch usage snapshots
        migrations.RemoveField(model_name='storeissuebatchusage', name='batch_no'),
        migrations.RemoveField(model_name='storeissuebatchusage', name='expiry_date'),
        migrations.RemoveField(model_name='storetransferbatchusage', name='batch_no'),
        migrations.RemoveField(model_name='storetransferbatchusage', name='expiry_date'),

        # 0029: GRN batch / expiry, product agri details
        migrations.RemoveField(model_name='goodsreceiveditem', name='batch_no'),
        migrations.RemoveField(model_name='goodsreceiveditem', name='expiry_date'),
        migrations.RemoveField(model_name='product', name='active_ingredient'),
        migrations.RemoveField(model_name='product', name='registration_no'),
        migrations.RemoveField(model_name='product', name='pack_size'),
        migrations.RemoveField(model_name='product', name='target_crops'),

        # 0028: stock batch / purchase item expiry, farmer details, harvest due date
        migrations.RemoveField(model_name='stockbatch', name='batch_no'),
        migrations.RemoveField(model_name='stockbatch', name='expiry_date'),
        migrations.RemoveField(model_name='purchaseitem', name='batch_no'),
        migrations.RemoveField(model_name='purchaseitem', name='expiry_date'),
        migrations.RemoveField(model_name='customer', name='village'),
        migrations.RemoveField(model_name='customer', name='main_crop'),
        migrations.RemoveField(model_name='customer', name='credit_limit'),
        migrations.RemoveField(model_name='sale', name='harvest_due_date'),
        migrations.RemoveField(model_name='sale', name='harvest_note'),
    ]
