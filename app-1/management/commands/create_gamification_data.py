from django.core.management.base import BaseCommand
from app.models import BadgeSet, Badge, WeeklyChallenge, LevelTitle, Milestone

class Command(BaseCommand):
    help = 'Create initial gamification data'

    def handle(self, *args, **kwargs):
        
        # ========================================== #
        # 1. BADGE SETS                             #
        # ========================================== #
        
        # Financial Master Set
        set1, created = BadgeSet.objects.get_or_create(
            name='Financial Master',
            defaults={
                'description': 'Master all aspects of financial management',
                'icon': '👑',
                'total_badges': 6,
                'reward_points': 150,
            }
        )
        
        badges_data = [
            {'name': 'First Expense', 'description': 'Logged your first expense', 'icon': '💰', 'order': 1, 'unlock_condition': 'expense_1'},
            {'name': 'Budget Creator', 'description': 'Created your first budget', 'icon': '📊', 'order': 2, 'unlock_condition': 'budget_creator'},
            {'name': 'Goal Achiever', 'description': 'Achieved your first goal', 'icon': '🎯', 'order': 3, 'unlock_condition': 'goal_achiever'},
            {'name': 'Streak Starter', 'description': '7 day streak', 'icon': '🔥', 'order': 4, 'unlock_condition': 'streak_7'},
            {'name': 'Saving Master', 'description': 'Saved Rs. 50,000+', 'icon': '💰', 'order': 5, 'unlock_condition': 'saving_50000'},
            {'name': 'Financial Freedom', 'description': 'Completed all badges', 'icon': '🚀', 'order': 6, 'unlock_condition': 'all_badges'},
        ]
        
        for data in badges_data:
            Badge.objects.get_or_create(
                badge_set=set1,
                name=data['name'],
                defaults=data
            )
            self.stdout.write(f'✅ Created badge: {data["name"]}')
        
        # ========================================== #
        # 2. WEEKLY CHALLENGES                      #
        # ========================================== #
        
        from datetime import date, timedelta
        
        challenges_data = [
            {
                'title': '💪 Saving Challenge',
                'description': 'Save Rs. 5,000 this week',
                'challenge_type': 'saving',
                'difficulty': 'medium',
                'target_value': 5000,
                'points_reward': 50,
                'bonus_points': 20,
                'start_date': date.today(),
                'end_date': date.today() + timedelta(days=7),
            },
            {
                'title': '📊 Expense Tracker',
                'description': 'Log 20 expenses this week',
                'challenge_type': 'expense',
                'difficulty': 'easy',
                'target_value': 20,
                'points_reward': 30,
                'bonus_points': 10,
                'start_date': date.today(),
                'end_date': date.today() + timedelta(days=7),
            },
            {
                'title': '🔥 Streak Master',
                'description': 'Maintain 7 day streak',
                'challenge_type': 'streak',
                'difficulty': 'medium',
                'target_value': 7,
                'points_reward': 60,
                'bonus_points': 25,
                'start_date': date.today(),
                'end_date': date.today() + timedelta(days=7),
            },
            {
                'title': '📋 Budget Expert',
                'description': 'Create 3 budgets this week',
                'challenge_type': 'budget',
                'difficulty': 'easy',
                'target_value': 3,
                'points_reward': 40,
                'bonus_points': 15,
                'start_date': date.today(),
                'end_date': date.today() + timedelta(days=7),
            },
        ]
        
        for data in challenges_data:
            challenge, created = WeeklyChallenge.objects.get_or_create(
                title=data['title'],
                defaults=data
            )
            self.stdout.write(f'✅ Created challenge: {challenge.title}')
        
        # ========================================== #
        # 3. LEVEL TITLES                           #
        # ========================================== #
        
        levels_data = [
            {'level_number': 1, 'title': '🐣 Beginner', 'xp_required': 0, 'icon': '🐣', 'benefits': 'Basic access'},
            {'level_number': 2, 'title': '📚 Learner', 'xp_required': 100, 'icon': '📚', 'benefits': 'Access to missions'},
            {'level_number': 3, 'title': '💪 Achiever', 'xp_required': 250, 'icon': '💪', 'benefits': 'Access to challenges'},
            {'level_number': 4, 'title': '🎯 Focused', 'xp_required': 500, 'icon': '🎯', 'benefits': 'Access to badges'},
            {'level_number': 5, 'title': '🏆 Winner', 'xp_required': 1000, 'icon': '🏆', 'benefits': 'Access to collections'},
            {'level_number': 6, 'title': '👑 Expert', 'xp_required': 2000, 'icon': '👑', 'benefits': 'Leaderboard access'},
            {'level_number': 7, 'title': '🌟 Master', 'xp_required': 5000, 'icon': '🌟', 'benefits': 'Premium features'},
            {'level_number': 8, 'title': '🔥 Legend', 'xp_required': 10000, 'icon': '🔥', 'benefits': 'All features unlocked'},
            {'level_number': 9, 'title': '🚀 Champion', 'xp_required': 25000, 'icon': '🚀', 'benefits': 'Invite-only events'},
            {'level_number': 10, 'title': '👑 Ultimate', 'xp_required': 50000, 'icon': '👑', 'benefits': 'Ultimate status'},
        ]
        
        for data in levels_data:
            level, created = LevelTitle.objects.get_or_create(
                level_number=data['level_number'],
                defaults=data
            )
            self.stdout.write(f'✅ Created level: Level {level.level_number} - {level.title}')
        
        # ========================================== #
        # 4. MILESTONES                            #
        # ========================================== #
        
        milestones_data = [
            {'name': 'First 10 Expenses', 'description': 'Logged 10 expenses', 'milestone_type': 'expense', 'target_value': 10, 'icon': '📊', 'points_reward': 10},
            {'name': '50 Expenses', 'description': 'Logged 50 expenses', 'milestone_type': 'expense', 'target_value': 50, 'icon': '📈', 'points_reward': 25},
            {'name': '100 Expenses', 'description': 'Logged 100 expenses', 'milestone_type': 'expense', 'target_value': 100, 'icon': '🔥', 'points_reward': 50},
            {'name': 'First 10,000 Savings', 'description': 'Saved Rs. 10,000', 'milestone_type': 'saving', 'target_value': 10000, 'icon': '💰', 'points_reward': 20},
            {'name': '50,000 Savings', 'description': 'Saved Rs. 50,000', 'milestone_type': 'saving', 'target_value': 50000, 'icon': '💰', 'points_reward': 50},
            {'name': '1,00,000 Savings', 'description': 'Saved Rs. 1,00,000', 'milestone_type': 'saving', 'target_value': 100000, 'icon': '🏆', 'points_reward': 100},
            {'name': '7 Day Streak', 'description': '7 day activity streak', 'milestone_type': 'streak', 'target_value': 7, 'icon': '🔥', 'points_reward': 25},
            {'name': '30 Day Streak', 'description': '30 day activity streak', 'milestone_type': 'streak', 'target_value': 30, 'icon': '⭐', 'points_reward': 75},
            {'name': '100 Day Streak', 'description': '100 day activity streak', 'milestone_type': 'streak', 'target_value': 100, 'icon': '👑', 'points_reward': 200},
        ]
        
        for data in milestones_data:
            milestone, created = Milestone.objects.get_or_create(
                name=data['name'],
                defaults=data
            )
            self.stdout.write(f'✅ Created milestone: {milestone.name}')
        
        self.stdout.write(self.style.SUCCESS('🎉 All gamification data created successfully!'))