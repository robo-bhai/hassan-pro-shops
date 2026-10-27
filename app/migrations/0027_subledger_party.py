# Step 4 - customer / vendor sub-ledger: party on journal lines and ledger rows

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0026_postingrule_glposting'),
    ]

    operations = [
        migrations.AddField(
            model_name='journalentryitem',
            name='customer',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='app.customer'),
        ),
        migrations.AddField(
            model_name='journalentryitem',
            name='vendor',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='app.vendor'),
        ),
        migrations.AddField(
            model_name='ledgerentry',
            name='customer',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='app.customer'),
        ),
        migrations.AddField(
            model_name='ledgerentry',
            name='vendor',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='app.vendor'),
        ),
        migrations.AddIndex(
            model_name='ledgerentry',
            index=models.Index(fields=['customer', 'date'], name='ledger_customer_date_idx'),
        ),
        migrations.AddIndex(
            model_name='ledgerentry',
            index=models.Index(fields=['vendor', 'date'], name='ledger_vendor_date_idx'),
        ),
    ]
