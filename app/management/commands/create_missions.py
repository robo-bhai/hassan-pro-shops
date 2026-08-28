from django.core.management.base import BaseCommand
from app.models import Mission, Achievement

class Command(BaseCommand):
    help = 'Create initial missions and achievements'

    def handle(self, *args, **kwargs):
        # Create Missions
        missions = [
            {
                'title': '💰 Daily Expense Tracker',
                'description': 'Log 3 expenses today',
                'mission_type': 'daily',
                'category': 'expense',
                'target_value': 3,
                'points_reward': 10,
            },
            {
                'title': '💵 Daily Saving Goal',
                'description': 'Save Rs. 500 today',
                'mission_type': 'daily',
                'category': 'saving',
                'target_value': 500,
                'points_reward': 15,
            },
            {
                'title': '📊 Budget Review',
                'description': 'Check your budget utilization',
                'mission_type': 'daily',
                'category': 'budget',
                'target_value': 1,
                'points_reward': 5,
            },
            {
                'title': '🔥 Streak Builder',
                'description': 'Log expenses for 7 days straight',
                'mission_type': 'weekly',
                'category': 'streak',
                'target_value': 7,
                'points_reward': 25,
            },
            {
                'title': '🏆 Saving Challenge',
                'description': 'Save Rs. 5,000 this week',
                'mission_type': 'weekly',
                'category': 'saving',
                'target_value': 5000,
                'points_reward': 50,
            },
        ]

        for mission_data in missions:
            mission, created = Mission.objects.get_or_create(
                title=mission_data['title'],
                defaults=mission_data
            )
            if created:
                self.stdout.write(f'✅ Created mission: {mission.title}')

        # Create Achievements
        achievements = [
            {'name': 'First Expense', 'description': 'Logged your first expense', 'achievement_type': 'first_expense', 'icon': '💰', 'points_reward': 10},
            {'name': 'Budget Creator', 'description': 'Created your first budget', 'achievement_type': 'budget_creator', 'icon': '📊', 'points_reward': 15},
            {'name': 'Goal Achiever', 'description': 'Achieved a budget goal', 'achievement_type': 'goal_achiever', 'icon': '🎯', 'points_reward': 20},
            {'name': '7 Day Streak', 'description': 'Maintained a 7-day activity streak', 'achievement_type': 'seven_day_streak', 'icon': '🔥', 'points_reward': 25},
            {'name': '30 Day Streak', 'description': 'Maintained a 30-day activity streak', 'achievement_type': 'thirty_day_streak', 'icon': '⭐', 'points_reward': 50},
            {'name': 'Saving Master', 'description': 'Saved Rs. 100,000+', 'achievement_type': 'saving_master', 'icon': '🏆', 'points_reward': 100},
            {'name': 'Expense Tracker', 'description': 'Logged 50+ expenses', 'achievement_type': 'expense_tracker', 'icon': '📈', 'points_reward': 30},
            {'name': 'Budget Expert', 'description': 'Completed 10+ budget goals', 'achievement_type': 'budget_expert', 'icon': '👑', 'points_reward': 75},
            {'name': 'Financial Freedom', 'description': 'Saved Rs. 500,000+', 'achievement_type': 'financial_freedom', 'icon': '🚀', 'points_reward': 200},
            {'name': 'Consistent Saver', 'description': 'Saved money for 30+ days', 'achievement_type': 'consistent_saver', 'icon': '💪', 'points_reward': 60},
        ]

        for ach_data in achievements:
            ach, created = Achievement.objects.get_or_create(
                achievement_type=ach_data['achievement_type'],
                defaults=ach_data
            )
            if created:
                self.stdout.write(f'✅ Created achievement: {ach.name}')

        self.stdout.write(self.style.SUCCESS('🎉 All missions and achievements created successfully!'))