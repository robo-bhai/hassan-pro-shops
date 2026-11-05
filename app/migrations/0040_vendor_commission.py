from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0039_vendor_portal'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendorprofile',
            name='commission_percent',
            field=models.DecimalField(
                blank=True, null=True, max_digits=5, decimal_places=2,
                verbose_name='Commission %',
                help_text='Shop is vendor ki har bikri par itna % rakhta hai. Khali = default '
                          '(settings.VENDOR_DEFAULT_COMMISSION_PERCENT, warna 10%)'),
        ),
    ]
