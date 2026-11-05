"""Remove the Stores module (store profiles, teams, issue, transfer, requests, counts, returns, settings).

WARNING: this drops the Store* tables, so all data in them is deleted.
Take a database backup before running `python manage.py migrate`.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0033_storeprofile_capabilities'),
    ]

    # children first, so no model is deleted while another still points to it
    operations = [
        migrations.DeleteModel(name='StoreReturnBatch'),
        migrations.DeleteModel(name='StoreReturnLine'),
        migrations.DeleteModel(name='StoreReturn'),
        migrations.DeleteModel(name='StoreCountLine'),
        migrations.DeleteModel(name='StoreCount'),
        migrations.DeleteModel(name='StoreIssueRequestItem'),
        migrations.DeleteModel(name='StoreIssueRequest'),
        migrations.DeleteModel(name='StoreJournalLink'),
        migrations.DeleteModel(name='StoreAccountRule'),
        migrations.DeleteModel(name='StoreSetting'),
        migrations.DeleteModel(name='StoreTransferBatchUsage'),
        migrations.DeleteModel(name='StoreTransferItem'),
        migrations.DeleteModel(name='StoreTransfer'),
        migrations.DeleteModel(name='StoreIssueBatchUsage'),
        migrations.DeleteModel(name='StoreIssueItem'),
        migrations.DeleteModel(name='StoreIssue'),
        migrations.DeleteModel(name='StoreMember'),
        migrations.DeleteModel(name='StoreProfile'),
    ]
