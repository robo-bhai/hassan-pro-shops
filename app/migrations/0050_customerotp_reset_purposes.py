from django.db import migrations, models


class Migration(migrations.Migration):
    """CustomerOTP.purpose mein 'rider_reset' aur 'admin_reset' (sirf choices, table nahi badalta)."""

    dependencies = [
        ('app', '0049_deliveryarea'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customerotp',
            name='purpose',
            field=models.CharField(
                choices=[
                    ('register', 'Registration'),
                    ('login', 'Login'),
                    ('forgot_password', 'Forgot Password'),
                    ('order', 'Order Verification'),
                    ('rider_reset', 'Rider Password Reset'),
                    ('admin_reset', 'Admin Password Reset'),
                ],
                default='register',
                max_length=20,
            ),
        ),
    ]
