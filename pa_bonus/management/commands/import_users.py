import os
import time
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.hashers import make_password
from django.db import transaction
from tablib import Dataset
from pa_bonus.models import User, Region
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Import users from an Excel file with improved performance'

    def add_arguments(self, parser):
        parser.add_argument('excel_file', type=str, help='Path to the Excel file')
        parser.add_argument(
            '--batch-size', 
            type=int, 
            default=100,
            help='Number of users to process in a single transaction'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Validate the import without committing changes to the database'
        )

    def handle(self, *args, **options):
        excel_file = options['excel_file']
        batch_size = options['batch_size']
        dry_run = options['dry_run']

        if not os.path.exists(excel_file):
            raise CommandError(f'Excel file not found: {excel_file}')

        # Load data with pandas for better performance
        start_time = time.time()
        self.stdout.write(f"Loading data from {excel_file}...")
        
        try:
            # Determine file format
            file_ext = os.path.splitext(excel_file)[1].lower()
            if file_ext == '.xlsx':
                df = pd.read_excel(excel_file)
            elif file_ext == '.csv':
                df = pd.read_csv(excel_file)
            else:
                raise CommandError(f"Unsupported file format: {file_ext}")
                
            # Convert all column names to lowercase
            df.columns = df.columns.str.lower()
            
            # Pre-cache regions for faster lookups
            self.stdout.write("Caching regions...")
            regions = {r.code: r for r in Region.objects.all()}
            
            # Validate required columns
            required_columns = ['email', 'username', 'user_number']
            missing = [col for col in required_columns if col not in df.columns]
            if missing:
                raise CommandError(f"Missing required columns: {', '.join(missing)}")
            
            # Process data in batches
            total_rows = len(df)
            self.stdout.write(f"Processing {total_rows} users in batches of {batch_size}...")
            
            # Prepare for statistics
            created_count = 0
            updated_count = 0
            error_count = 0
            errors = []
            
            # Process in batches
            for batch_start in range(0, total_rows, batch_size):
                batch_end = min(batch_start + batch_size, total_rows)
                self.stdout.write(f"Processing batch {batch_start + 1}-{batch_end} of {total_rows}")
                
                batch_df = df.iloc[batch_start:batch_end]
                
                # Use a transaction for each batch
                with transaction.atomic():
                    if dry_run:
                        # In dry run mode, we'll just validate each row
                        self.stdout.write("Validating batch (dry run)...")
                        for _, row in batch_df.iterrows():
                            try:
                                self._validate_user_row(row, regions)
                            except Exception as e:
                                error_count += 1
                                errors.append(f"Row with email {row.get('email', 'unknown')}: {str(e)}")
                    else:
                        # Actually process each row in the batch
                        for _, row in batch_df.iterrows():
                            try:
                                result = self._process_user_row(row, regions)
                                if result == 'created':
                                    created_count += 1
                                elif result == 'updated':
                                    updated_count += 1
                            except Exception as e:
                                error_count += 1
                                errors.append(f"Row with email {row.get('email', 'unknown')}: {str(e)}")
                                logger.error(f"Error processing user: {str(e)}", exc_info=True)
            
            # Report results
            elapsed_time = time.time() - start_time
            self.stdout.write(self.style.SUCCESS(
                f"Import completed in {elapsed_time:.2f} seconds.\n"
                f"Created: {created_count}, Updated: {updated_count}, Errors: {error_count}"
            ))
            
            if error_count > 0:
                self.stdout.write(self.style.WARNING("Errors encountered:"))
                for error in errors[:10]:  # Show first 10 errors
                    self.stdout.write(f"  - {error}")
                
                if len(errors) > 10:
                    self.stdout.write(f"  ...and {len(errors) - 10} more errors")
                    
        except Exception as e:
            raise CommandError(f"Error importing users: {str(e)}")
    
    def _validate_user_row(self, row, regions_cache):
        """
        Validate a single user row without writing to database.
        """
        # Check required fields
        for field in ['email', 'username', 'user_number']:
            if pd.isna(row.get(field)) or not row.get(field):
                raise ValueError(f"Missing required field: {field}")
        
        # Validate region if present
        if not pd.isna(row.get('region')) and row.get('region'):
            region_code = str(row.get('region'))
            if region_code not in regions_cache:
                raise ValueError(f"Region with code '{region_code}' does not exist")
        
        # Check if email is valid
        email = row.get('email')
        if '@' not in email:
            raise ValueError(f"Invalid email format: {email}")
        
        # Check if user_number is unique (if the user doesn't exist)
        user_number = str(row.get('user_number'))
        email_exists = User.objects.filter(email=email).exists()
        
        if not email_exists:
            user_number_exists = User.objects.filter(user_number=user_number).exists()
            if user_number_exists:
                raise ValueError(f"User number {user_number} already exists")
    
    def _process_user_row(self, row, regions_cache):
        """
        Process a single user row and create/update the user.
        Returns 'created' or 'updated' based on the action taken.
        """
        email = row.get('email')
        
        # Prepare user data
        user_data = {
            'username': row.get('username'),
            'first_name': row.get('first_name', ''),
            'last_name': row.get('last_name', ''),
            'user_number': str(row.get('user_number')),
            'is_active': bool(row.get('is_active', True)),
        }
        
        # Handle optional fields
        if not pd.isna(row.get('user_phone')):
            user_data['user_phone'] = str(row.get('user_phone'))
        
        # Handle region
        if not pd.isna(row.get('region')) and row.get('region'):
            region_code = str(row.get('region'))
            if region_code in regions_cache:
                user_data['region'] = regions_cache[region_code]
            else:
                # Skip this field if region is invalid
                pass
        
        # Handle password - hash it efficiently
        if not pd.isna(row.get('password')) and row.get('password'):
            user_data['password'] = make_password(str(row.get('password')))
        else:
            # Default password is user_number
            user_data['password'] = make_password(str(row.get('user_number')))
        
        # Create or update user
        user, created = User.objects.update_or_create(
            email=email,
            defaults=user_data
        )
        
        return 'created' if created else 'updated'