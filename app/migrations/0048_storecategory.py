import django.db.models.deletion
from django.db import migrations, models

DEFAULTS = [
    ('Restaurants', '🍔'), ('Grocery', '🛒'), ('Pharmacy', '💊'), ('Bakery & Sweets', '🍰'),
    ('Fashion', '👗'), ('Electronics', '📱'), ('Home & Kitchen', '🏠'), ('Other', '🏪'),
]


def seed(apps, schema_editor):
    StoreCategory = apps.get_model('app', 'StoreCategory')
    for i, (name, icon) in enumerate(DEFAULTS):
        StoreCategory.objects.get_or_create(name=name, defaults={'icon': icon, 'sort_order': i})


def unseed(apps, schema_editor):
    pass  # categories delete nahi karte (admin ne edit kar rakhi ho sakti hain)


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0047_order_review'),
    ]

    operations = [
        migrations.CreateModel(
            name='StoreCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=60, unique=True)),
                ('icon', models.CharField(blank=True, default='🏪', help_text='Ek emoji, jaise 🍔 🛒 💊', max_length=8)),
                ('sort_order', models.PositiveSmallIntegerField(default=0, help_text='Chhota number pehle nazar aata hai')),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Store Category',
                'verbose_name_plural': '3.1 Store Categories',
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.AddField(
            model_name='vendorprofile',
            name='store_category',
            field=models.ForeignKey(blank=True, help_text='Store ki type (Restaurant, Grocery...). Customer stores isi se filter karta hai.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stores', to='app.storecategory', verbose_name='Store category'),
        ),
        migrations.RunPython(seed, unseed),
    ]
