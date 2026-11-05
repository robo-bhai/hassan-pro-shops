# OCR scan log + alias suggestions (alias learning)
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0030_agri_usage_snapshot'),
    ]

    operations = [
        migrations.CreateModel(
            name='OcrScanLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source', models.CharField(choices=[('camera', 'Live camera'), ('photo', 'Photo'), ('manual', 'Typed')], default='camera', max_length=10)),
                ('raw_text', models.CharField(blank=True, default='', max_length=400)),
                ('text', models.CharField(blank=True, default='', max_length=200)),
                ('ocr_conf', models.SmallIntegerField(blank=True, null=True)),
                ('warehouse_id', models.IntegerField(blank=True, null=True)),
                ('candidates', models.SmallIntegerField(default=0)),
                ('top_score', models.SmallIntegerField(default=0)),
                ('confident', models.BooleanField(default=False)),
                ('outcome', models.CharField(choices=[('pending', 'Shown, no action yet'), ('no_match', 'No product found'), ('auto_added', 'Added automatically'), ('tapped_top', 'Cashier tapped the first match'), ('corrected', 'Cashier chose another product')], default='pending', max_length=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('chosen_product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='app.product')),
                ('top_product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='app.product')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'OCR scan log',
                'ordering': ['-created_at', '-id'],
                'indexes': [models.Index(fields=['created_at'], name='app_ocrscan_created_idx'),
                            models.Index(fields=['outcome'], name='app_ocrscan_outcome_idx')],
            },
        ),
        migrations.CreateModel(
            name='OcrAliasSuggestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.CharField(max_length=100)),
                ('hits', models.PositiveIntegerField(default=1)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved (alias created)'), ('rejected', 'Rejected')], default='pending', max_length=10)),
                ('first_seen', models.DateTimeField(auto_now_add=True)),
                ('last_seen', models.DateTimeField(auto_now=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ocr_alias_suggestions', to='app.product')),
            ],
            options={
                'verbose_name_plural': 'OCR alias suggestions',
                'ordering': ['-hits', '-last_seen'],
                'unique_together': {('product', 'text')},
            },
        ),
    ]
