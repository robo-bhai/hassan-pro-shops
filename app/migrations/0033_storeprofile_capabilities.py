from django.db import migrations, models


def copy_can_issue(apps, schema_editor):
    """Old stores: 'send goods' used to follow can_issue, so keep exactly that behaviour."""
    StoreProfile = apps.get_model('app', 'StoreProfile')
    StoreProfile.objects.filter(can_issue=False).update(can_transfer_out=False)


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0032_remove_agri_edition'),
    ]

    operations = [
        migrations.AddField(
            model_name='storeprofile', name='can_transfer_out',
            field=models.BooleanField(default=True, help_text='This store can send goods to other stores')),
        migrations.AddField(
            model_name='storeprofile', name='can_transfer_in',
            field=models.BooleanField(default=True, help_text='This store can receive goods from other stores')),
        migrations.AddField(
            model_name='storeprofile', name='can_receive_purchase',
            field=models.BooleanField(default=True, help_text='Purchase / GRN goods can be received in this store')),
        migrations.AddField(
            model_name='storeprofile', name='can_count',
            field=models.BooleanField(default=True, help_text='Physical stock count is allowed in this store')),
        migrations.AddField(
            model_name='storeprofile', name='can_return',
            field=models.BooleanField(default=True, help_text='Goods can be returned back to this store')),
        migrations.RunPython(copy_can_issue, migrations.RunPython.noop),
    ]
