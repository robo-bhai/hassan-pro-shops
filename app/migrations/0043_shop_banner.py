from django.core.validators import RegexValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0042_saleorder_vendor'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopBanner',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(help_text='Sirf admin ke liye naam; image ka alt text bhi yahi banta hai', max_length=100)),
                ('image', models.ImageField(help_text='Behtareen size: 1200 x 400 px (3:1), JPG ya PNG', upload_to='shop_banners/')),
                ('link_url', models.CharField(blank=True, default='', help_text='Optional: apni site ka path (/shop/stores/?free=1) ya https:// link. Store select ho to uska page pehle aata hai', max_length=300, validators=[RegexValidator('^(/(?!/)|https://)', message="Link '/' se (apni site ka path, jaise /shop/stores/?free=1) ya 'https://' se shuru hona chahiye.")])),
                ('is_active', models.BooleanField(default=True)),
                ('starts_on', models.DateField(blank=True, help_text='Khali = abhi se', null=True)),
                ('ends_on', models.DateField(blank=True, help_text='Khali = hamesha', null=True)),
                ('sort_order', models.PositiveSmallIntegerField(default=0, help_text='Chota number pehle dikhta hai')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('store', models.ForeignKey(blank=True, help_text='Optional: banner par click karne se is store ka page khulega', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='banners', to='app.vendorprofile')),
            ],
            options={
                'verbose_name': 'Shop Banner',
                'verbose_name_plural': 'Shop Banners',
                'ordering': ['sort_order', '-created_at'],
            },
        ),
    ]
