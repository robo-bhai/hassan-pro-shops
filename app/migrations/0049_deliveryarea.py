from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0048_storecategory'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeliveryArea',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('city', models.CharField(db_index=True, max_length=100)),
                ('name', models.CharField(help_text='Area, mohalla ya gaon ka naam', max_length=100)),
                ('sort_order', models.PositiveSmallIntegerField(default=0, help_text='Chhota number pehle nazar aata hai')),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Delivery Area',
                'verbose_name_plural': '3.3 Delivery Areas',
                'ordering': ['city', 'sort_order', 'name'],
                'unique_together': {('city', 'name')},
            },
        ),
    ]
