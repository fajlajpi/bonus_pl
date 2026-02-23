import logging
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from django.db import transaction
from pa_bonus.models import User

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Reset user passwords to their default values (user_number)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually changing passwords'
        )
        parser.add_argument(
            '--default-password',
            type=str,
            help='Set a specific default password instead of using user_number'
        )
        parser.add_argument(
            '--user-emails',
            nargs='+',
            type=str,
            help='Reset passwords only for specific users by email'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        default_password = options.get('default_password')
        user_emails = options.get('user_emails')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('Running in DRY RUN mode - no changes will be made'))
        
        # Get all users or filter by email if specified
        users_query = User.objects.all()
        if user_emails:
            self.stdout.write(f"Filtering to {len(user_emails)} specified users")
            users_query = users_query.filter(email__in=user_emails)
        
        # Count for statistics
        total_users = users_query.count()
        reset_count = 0
        skipped_count = 0
        
        # Process in batches for better performance
        batch_size = 100
        
        self.stdout.write(f"About to process {total_users} users")
        
        # Process all users in batches within a transaction
        for i in range(0, total_users, batch_size):
            with transaction.atomic():
                batch = users_query[i:i+batch_size]
                self.stdout.write(f"Processing batch {i+1}-{min(i+batch_size, total_users)} of {total_users}")
                
                for user in batch:
                    # Determine the new password
                    if default_password:
                        new_password = default_password
                    elif user.user_number:
                        new_password = user.user_number
                    elif user.username:
                        new_password = user.username
                    else:
                        self.stdout.write(self.style.WARNING(
                            f"Skipping user {user.email} - no valid default password source"
                        ))
                        skipped_count += 1
                        continue
                    
                    # Set the new password (hashed)
                    if not dry_run:
                        user.password = make_password(new_password)
                        user.save(update_fields=['password'])
                    
                    reset_count += 1
                    self.stdout.write(
                        f"{'Would reset' if dry_run else 'Reset'} password for {user.email} "
                        f"to {'<custom>' if default_password else new_password}"
                    )
        
        # Print summary
        self.stdout.write(self.style.SUCCESS(
            f"{'Would have reset' if dry_run else 'Reset'} {reset_count} passwords "
            f"({skipped_count} users skipped)"
        ))
        
        if dry_run:
            self.stdout.write(self.style.WARNING(
                "This was a dry run! No changes were made. "
                "Run without --dry-run to apply changes."
            ))