from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0038_rename_app_pricech_product_6d1f0a_idx_app_pricech_product_167785_idx_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='VendorProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('business_name', models.CharField(max_length=100)),
                ('city', models.CharField(blank=True, default='', max_length=100)),
                ('is_approved', models.BooleanField(default=False, help_text='Approved vendor hi products list kar sakta hai', verbose_name='Approved')),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('last_login_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='vendor_profile', to=settings.AUTH_USER_MODEL)),
                ('vendor', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='portal_profile', to='app.vendor')),
            ],
            options={
                'verbose_name_plural': '3.2 Vendor Portal Accounts',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='product',
            name='vendor',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='listed_products', to='app.vendor', verbose_name='Listed by Vendor'),
        ),
        migrations.AddField(
            model_name='product',
            name='approval_status',
            field=models.CharField(choices=[('approved', 'Approved'), ('pending', 'Pending'), ('rejected', 'Rejected')], default='approved', help_text='Vendor ke products pending se shuru hote hain; approve hone par shop par nazar aate hain', max_length=10, verbose_name='Approval Status'),
        ),
        migrations.AddField(
            model_name='product',
            name='rejection_reason',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.CreateModel(
            name='VendorSubmission',
            fields=[],
            options={
                'verbose_name': 'Vendor Product Submission',
                'verbose_name_plural': '3.3 Vendor Product Submissions',
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('app.product',),
        ),
    ]
