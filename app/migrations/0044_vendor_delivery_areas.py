from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0043_shop_banner'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendorprofile',
            name='delivery_areas',
            field=models.TextField(
                blank=True, default='', max_length=1000,
                help_text='Wo shehar/area jahan ye store deliver karta hai, comma se alag (jaise: Gulberg, DHA, Johar Town). Khali = sirf store ke shehar mein.',
            ),
        ),
    ]
