# Agri Edition: batch no / expiry copied onto store issue + transfer batch usages
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0029_agri_complete'),
    ]

    operations = [
        migrations.AddField(model_name='storeissuebatchusage', name='batch_no',
                            field=models.CharField(blank=True, max_length=50, null=True)),
        migrations.AddField(model_name='storeissuebatchusage', name='expiry_date',
                            field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name='storetransferbatchusage', name='batch_no',
                            field=models.CharField(blank=True, max_length=50, null=True)),
        migrations.AddField(model_name='storetransferbatchusage', name='expiry_date',
                            field=models.DateField(blank=True, null=True)),
    ]
