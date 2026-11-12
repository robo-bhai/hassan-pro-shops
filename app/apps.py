from django.apps import AppConfig


class AppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app'

    def ready(self):
        import app.signals
        import app.security.signals_security  
        import app.ledger.signals_gl
        import app.order_status_emails   # customer ko order status email
