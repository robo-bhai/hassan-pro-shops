"""
Auto-close inactive chat conversations
Run daily via cron or celery

Usage:
    python manage.py close_old_chats
    python manage.py close_old_chats --hours=48
"""
from django.core.management.base import BaseCommand
from django.utils.timezone import now
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Auto-close chats inactive for 24+ hours'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Hours of inactivity before closing (default: 24)'
        )
    
    def handle(self, *args, **options):
        from app.models import ChatConversation
        
        hours = options['hours']
        cutoff = now() - timedelta(hours=hours)
        
        # Get old active chats
        old_chats = ChatConversation.objects.filter(
            status='active',
            last_message_at__lt=cutoff
        )
        
        count = old_chats.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('✅ No inactive chats to close'))
            return
        
        # Close them
        old_chats.update(
            status='closed',
            closed_at=now()
        )
        
        self.stdout.write(self.style.SUCCESS(
            f'✅ Closed {count} inactive chats (older than {hours} hours)'
        ))
        
        logger.info(f"Auto-closed {count} inactive chat conversations")