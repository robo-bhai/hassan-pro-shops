# Minimum margin policy (Step 3 of the pricing upgrade): one optional column on Category.
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0035_pricechangelog'),
    ]

    operations = [
        migrations.AddField(
            model_name='category',
            name='min_margin_percent',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Lowest profit (as % of cost) allowed for products of this category. Empty = use the company rule (Settings > Pricing). 0 = no minimum for this category.', max_digits=6, null=True, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Minimum margin %'),
        ),
    ]
