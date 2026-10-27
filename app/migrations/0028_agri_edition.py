# Agri Edition: expiry/batch on stock, farmer details on customers, harvest due date on sales
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0027_subledger_party'),
    ]

    operations = [
        migrations.AddField(model_name='stockbatch', name='batch_no',
                            field=models.CharField(blank=True, db_index=True, max_length=50, null=True)),
        migrations.AddField(model_name='stockbatch', name='expiry_date',
                            field=models.DateField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name='purchaseitem', name='batch_no',
                            field=models.CharField(blank=True, max_length=50, null=True)),
        migrations.AddField(model_name='purchaseitem', name='expiry_date',
                            field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name='customer', name='village',
                            field=models.CharField(blank=True, max_length=100, null=True)),
        migrations.AddField(model_name='customer', name='main_crop',
                            field=models.CharField(blank=True, max_length=100, null=True)),
        migrations.AddField(model_name='customer', name='credit_limit',
                            field=models.DecimalField(decimal_places=2, default=0, max_digits=15)),
        migrations.AddField(model_name='sale', name='harvest_due_date',
                            field=models.DateField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name='sale', name='harvest_note',
                            field=models.CharField(blank=True, default='', max_length=200)),
    ]
