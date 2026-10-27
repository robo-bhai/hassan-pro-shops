from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0022_merge_20261019_0649'),
    ]

    operations = [
        migrations.CreateModel(
            name='MonthlyPlanBatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('batch_no', models.CharField(default='', editable=False, max_length=20, unique=True)),
                ('title', models.CharField(blank=True, default='', max_length=200)),
                ('month', models.DateField(help_text='First day of the month')),
                ('notes', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_plan_batches', to=settings.AUTH_USER_MODEL)),
                ('warehouse', models.ForeignKey(blank=True, help_text='Warehouse used for all lines', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='plan_batches', to='app.warehouse')),
            ],
            options={
                'verbose_name_plural': '📦 Multi-Product Monthly Plans',
                'ordering': ['-month', '-id'],
            },
        ),
        migrations.AddField(
            model_name='monthlypurchaseplan',
            name='batch',
            field=models.ForeignKey(blank=True, help_text='Multi-product plan this line belongs to', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='app.monthlyplanbatch'),
        ),
    ]
