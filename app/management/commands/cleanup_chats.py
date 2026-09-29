"""
Chat Cleanup Management Command
================================
Auto-delete empty chats and close stale active chats

Usage:
    python manage.py cleanup_chats
    python manage.py cleanup_chats --hours=24
    python manage.py cleanup_chats --delete-empty
    python manage.py cleanup_chats --hours=1 --delete-empty --verbose
"""
from django.core.management.base import BaseCommand
from django.utils.timezone import now
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Auto-cleanup empty and stale chat conversations'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=1,
            help='Hours of inactivity before closing (default: 1)'
        )
        parser.add_argument(
            '--delete-empty',
            action='store_true',
            help='Delete chats with no messages'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Test without making changes'
        )
    
    def handle(self, *args, **options):
        from app.models import ChatConversation
        
        hours = options['hours']
        delete_empty = options['delete_empty']
        verbose = options['verbose']
        dry_run = options['dry_run']
        
        cutoff = now() - timedelta(hours=hours)
        
        self.stdout.write(self.style.WARNING('=' * 60))
        self.stdout.write(self.style.WARNING('  🧹 CHAT CLEANUP'))
        self.stdout.write(self.style.WARNING('=' * 60))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n⚠️ DRY RUN MODE — No changes will be made\n'))
        
        # ========================================== #
        # 1. DELETE EMPTY CHATS                      #
        # ========================================== #
        if delete_empty:
            empty_chats = ChatConversation.objects.filter(messages__isnull=True)
            empty_count = empty_chats.count()
            
            if verbose:
                self.stdout.write(f'\n🗑️  Found {empty_count} empty chats')
                for chat in empty_chats[:10]:
                    self.stdout.write(f'   #{chat.id} - {chat.get_display_name()}')
            
            if empty_count > 0:
                if not dry_run:
                    empty_chats.delete()
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Deleted {empty_count} empty chats')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'   [DRY] Would delete {empty_count} chats')
                    )
            else:
                self.stdout.write(self.style.SUCCESS('✅ No empty chats to delete'))
        
        # ========================================== #
        # 2. CLOSE STALE CHATS                       #
        # ========================================== #
        stale_chats = ChatConversation.objects.filter(
            status='active',
            last_message_at__lt=cutoff
        )
        stale_count = stale_chats.count()
        
        if verbose:
            self.stdout.write(f'\n⏰ Found {stale_count} stale chats (>{hours}h)')
            for chat in stale_chats[:10]:
                delta = now() - chat.last_message_at
                hours_ago = int(delta.total_seconds() / 3600)
                self.stdout.write(f'   #{chat.id} - {chat.get_display_name()} - {hours_ago}h ago')
        
        if stale_count > 0:
            if not dry_run:
                stale_chats.update(status='closed', closed_at=now())
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Closed {stale_count} stale chats')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'   [DRY] Would close {stale_count} chats')
                )
        else:
            self.stdout.write(self.style.SUCCESS('✅ No stale chats to close'))
        
        # ========================================== #
        # 3. FINAL STATS                             #
        # ========================================== #
        self.stdout.write(self.style.WARNING('\n' + '=' * 60))
        self.stdout.write(self.style.WARNING('  📊 FINAL STATUS'))
        self.stdout.write(self.style.WARNING('=' * 60))
        
        total = ChatConversation.objects.count()
        active = ChatConversation.objects.filter(status='active').count()
        closed = ChatConversation.objects.filter(status='closed').count()
        
        self.stdout.write(f'   Total: {total}')
        self.stdout.write(f'   Active: {active}')
        self.stdout.write(f'   Closed: {closed}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n⚠️ DRY RUN — No changes made'))
        
        self.stdout.write(self.style.SUCCESS('\n✅ Cleanup complete!\n'))