import os
import csv
import time
import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.hashers import make_password
from django.db import transaction, connection
from django.db.models import signals
from pa_bonus.models import User, Region

class Command(BaseCommand):
    help = 'Import users with high performance (1000+ users per minute)'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the CSV/Excel file')
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='Number of users to process in a single transaction'
        )
        parser.add_argument(
            '--password-column',
            type=str,
            default='password',
            help='Column name for password (default: "password")'
        )
        parser.add_argument(
            '--no-signals',
            action='store_true',
            help='Disable signals during import for better performance'
        )

    def handle(self, *args, **options):
        file_path = options['file_path']
        batch_size = options['batch_size']
        password_column = options['password_column']
        disable_signals = options['no_signals']

        if not os.path.exists(file_path):
            raise CommandError(f"File not found: {file_path}")

        # Get file extension to determine file type
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()

        # Load data
        self.stdout.write(f"Loading data from {file_path}...")
        try:
            if ext in ['.csv']:
                df = pd.read_csv(file_path)
            elif ext in ['.xlsx', '.xls']:
                df = pd.read_excel(file_path)
            else:
                raise CommandError(f"Unsupported file format: {ext}")
        except Exception as e:
            raise CommandError(f"Error reading file: {e}")

        # Convert column names to lowercase
        df.columns = [col.lower() for col in df.columns]
        total_rows = len(df)
        self.stdout.write(f"Found {total_rows} records to import")

        # Preload regions for faster lookup
        regions = {region.code: region for region in Region.objects.all()}
        self.stdout.write(f"Loaded {len(regions)} regions for lookup")

        # Setup to disable signals if requested
        user_signals = []
        if disable_signals:
            # Save all signal connections
            user_signals = [
                (getattr(signals, signal_name), 
                 getattr(signals, signal_name)._live_receivers(User))
                for signal_name in ['pre_save', 'post_save']
            ]
            # Disconnect signals
            for signal, _ in user_signals:
                signal.receivers = []
            self.stdout.write("Signals temporarily disabled for performance")

        # Optimize database for bulk operations
        self.optimize_database()

        total_time_start = time.time()
        created = 0
        updated = 0
        skipped = 0
        error_count = 0

        try:
            # Process in batches
            for batch_start in range(0, total_rows, batch_size):
                batch_end = min(batch_start + batch_size, total_rows)
                self.stdout.write(f"Processing batch {batch_start+1}-{batch_end} of {total_rows}")
                
                batch_time_start = time.time()
                batch_df = df.iloc[batch_start:batch_end]
                
                # Process the batch in a transaction
                with transaction.atomic():
                    for _, row in batch_df.iterrows():
                        try:
                            # Extract required fields
                            email = self.safe_get(row, 'email')
                            if not email:
                                self.stdout.write(self.style.WARNING(f"Skipping row - no email provided"))
                                skipped += 1
                                continue
                            
                            # Prepare user data
                            user_data = {
                                'username': self.safe_get(row, 'username', email),
                                'first_name': self.safe_get(row, 'first_name', ''),
                                'last_name': self.safe_get(row, 'last_name', ''),
                                'user_number': str(self.safe_get(row, 'user_number', '')),
                                'user_phone': str(self.safe_get(row, 'user_phone', '')),
                                'is_active': bool(self.safe_get(row, 'is_active', True)),
                            }
                            
                            # Handle password
                            password = self.safe_get(row, password_column)
                            if password:
                                user_data['password'] = make_password(str(password))
                            else:
                                # Use user_number as default password
                                user_data['password'] = make_password(str(user_data['user_number']))
                            
                            # Handle region
                            region_code = self.safe_get(row, 'region')
                            if region_code and str(region_code) in regions:
                                user_data['region'] = regions[str(region_code)]
                            
                            # Create or update user
                            user, is_created = User.objects.update_or_create(
                                email=email,
                                defaults=user_data
                            )
                            
                            if is_created:
                                created += 1
                            else:
                                updated += 1
                                
                        except Exception as e:
                            error_count += 1
                            self.stdout.write(self.style.ERROR(f"Error processing row: {e}"))
                
                batch_time = time.time() - batch_time_start
                rows_per_second = len(batch_df) / batch_time if batch_time > 0 else 0
                self.stdout.write(f"Batch processed in {batch_time:.2f}s ({rows_per_second:.1f} rows/second)")
        
        finally:
            # Restore database settings
            self.restore_database()
            
            # Restore signals if they were disabled
            if disable_signals:
                for signal, receivers in user_signals:
                    signal.receivers = receivers
                self.stdout.write("Signals restored")
        
        total_time = time.time() - total_time_start
        rows_per_second = total_rows / total_time if total_time > 0 else 0
        
        self.stdout.write(self.style.SUCCESS(
            f"Import completed in {total_time:.2f}s ({rows_per_second:.1f} rows/second)\n"
            f"Created: {created}, Updated: {updated}, Skipped: {skipped}, Errors: {error_count}"
        ))

    def safe_get(self, row, column, default=None):
        """Safely get a value from a pandas row."""
        if column in row and pd.notna(row[column]):
            return row[column]
        return default

    def optimize_database(self):
        """Optimize database settings for bulk imports."""
        cursor = connection.cursor()
        self.original_db_settings = {}
        
        try:
            if connection.vendor == 'postgresql':
                # PostgreSQL optimizations
                settings = [
                    ('synchronous_commit', 'OFF'),
                    ('full_page_writes', 'OFF'),
                    ('wal_buffers', '16MB'),
                    ('work_mem', '64MB'),
                ]
                
                for name, value in settings:
                    cursor.execute(f"SHOW {name}")
                    self.original_db_settings[name] = cursor.fetchone()[0]
                    cursor.execute(f"SET {name} = {value}")
                    
            elif connection.vendor == 'mysql':
                # MySQL optimizations
                cursor.execute("SET SESSION autocommit=0")
                cursor.execute("SET SESSION unique_checks=0")
                cursor.execute("SET SESSION foreign_key_checks=0")
            
            self.stdout.write("Database optimized for bulk import")
            
        except Exception as e:
            self.stdout.write(f"Warning: Could not optimize database settings: {e}")

    def restore_database(self):
        """Restore original database settings."""
        cursor = connection.cursor()
        
        try:
            if connection.vendor == 'postgresql':
                # Restore PostgreSQL settings
                for name, value in self.original_db_settings.items():
                    cursor.execute(f"SET {name} = '{value}'")
                    
            elif connection.vendor == 'mysql':
                # Restore MySQL settings
                cursor.execute("SET SESSION autocommit=1")
                cursor.execute("SET SESSION unique_checks=1")
                cursor.execute("SET SESSION foreign_key_checks=1")
                
            self.stdout.write("Restored original database settings")
            
        except Exception as e:
            self.stdout.write(f"Warning: Could not restore database settings: {e}")