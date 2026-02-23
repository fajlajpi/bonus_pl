import os
import shutil
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from tablib import Dataset
from pa_bonus.resources import RewardResource
from pa_bonus.models import Reward


class Command(BaseCommand):
    help = 'Import rewards from an Excel file, with optional image directory'

    def add_arguments(self, parser):
        parser.add_argument('excel_file', type=str, help='Path to the Excel file')
        parser.add_argument(
            '--image-dir', 
            type=str, 
            help='Path to directory containing images (named as ABRA_CODE.png)',
            required=False
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Validate the import without committing changes to the database'
        )

    def handle(self, *args, **options):
        excel_file = options['excel_file']
        image_dir = options.get('image_dir')
        dry_run = options.get('dry_run', False)

        # Verify the Excel file exists
        if not os.path.exists(excel_file):
            raise CommandError(f'Excel file not found: {excel_file}')

        # If image directory is provided, copy images to the expected location
        if image_dir and os.path.exists(image_dir):
            self.copy_images(image_dir)

        # Perform the import
        self.import_rewards(excel_file, dry_run)

    def copy_images(self, image_dir):
        """
        Copy images from the source directory to the expected location.
        
        Images should be named as ABRA_CODE.png in the source directory.
        """
        self.stdout.write('Copying images...')
        
        # Target directory for images
        target_dir = os.path.join(settings.MEDIA_ROOT, 'reward_import_images')
        
        # Create target directory if it doesn't exist
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
        
        # Get all image files from the source directory
        image_files = [f for f in os.listdir(image_dir) 
                      if os.path.isfile(os.path.join(image_dir, f)) and 
                      f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        
        # Count of successfully copied images
        copied_count = 0
        
        # Copy each image to the target directory
        for img_file in image_files:
            source_path = os.path.join(image_dir, img_file)
            
            # Get ABRA code from filename (remove extension)
            abra_code = os.path.splitext(img_file)[0]
            
            # Skip placeholder files if they exist
            if img_file.endswith('.placeholder'):
                continue
                
            # Always use PNG as the target format
            target_path = os.path.join(target_dir, f"{abra_code}.png")
            
            try:
                shutil.copy2(source_path, target_path)
                self.stdout.write(self.style.SUCCESS(f'Copied image for {abra_code}'))
                copied_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error copying image for {abra_code}: {e}'))
                
        self.stdout.write(self.style.SUCCESS(f'Copied {copied_count} images'))

    def import_rewards(self, excel_file, dry_run=False):
        """
        Import rewards from an Excel file.
        
        Args:
            excel_file: Path to the Excel file
            dry_run: If True, validate the import without committing changes
        """
        self.stdout.write(f'Importing rewards from {excel_file}...')
        
        # Create a dataset from the Excel file
        dataset = None
        file_extension = os.path.splitext(excel_file)[1].lower()
        
        try:
            with open(excel_file, 'rb') as f:
                if file_extension == '.xlsx':
                    import openpyxl
                    dataset = Dataset().load(f.read(), format='xlsx')
                elif file_extension == '.xls':
                    dataset = Dataset().load(f.read(), format='xls')
                elif file_extension == '.csv':
                    dataset = Dataset().load(f.read().decode('utf-8'), format='csv')
                else:
                    raise CommandError(f'Unsupported file format: {file_extension}')
        except Exception as e:
            raise CommandError(f'Error reading file: {str(e)}')
            
        if not dataset:
            raise CommandError('Failed to load dataset from file')
            
        # Skip Excel metadata rows if present
        if dataset.height > 0 and 'abra_code' not in dataset.headers:
            # First row might be a header row in a different format
            # Try using the first row as headers
            headers = [str(h).lower() for h in dataset[0]]
            if 'abra_code' in headers:
                dataset.headers = headers
                dataset.pop(0)  # Remove the header row from data
            else:
                raise CommandError('Could not find required "abra_code" column in the file')
        
        # Create resource instance
        resource = RewardResource()
        
        # Test data import (dry run)
        result = resource.import_data(dataset, dry_run=True)
        
        if result.has_errors():
            self.stdout.write(self.style.ERROR('Import validation failed!'))
            for error in result.row_errors():
                row_number, errors = error
                for err in errors:
                    self.stdout.write(self.style.ERROR(
                        f'Row {row_number}: {err.error}'
                    ))
            return
        
        # Report what would be done
        new_count = result.totals.get('new', 0)
        update_count = result.totals.get('update', 0)
        self.stdout.write(self.style.SUCCESS(
            f'Import validation successful. Would create {new_count} '
            f'new rewards, update {update_count} existing rewards.'
        ))
        
        # If this is not a dry run, perform the actual import
        if not dry_run:
            result = resource.import_data(dataset, dry_run=False)
            
            # Add image for each imported/updated reward
            self.process_images_after_import(dataset)
            
            new_count = result.totals.get('new', 0)
            update_count = result.totals.get('update', 0)
            self.stdout.write(self.style.SUCCESS(
                f'Successfully imported {new_count} new rewards, '
                f'updated {update_count} existing rewards.'
            ))
            
            # Report rewards without images
            rewards_without_images = Reward.objects.filter(image='')
            if rewards_without_images.exists():
                self.stdout.write(self.style.WARNING(
                    f'{rewards_without_images.count()} rewards have no associated image:'
                ))
                for reward in rewards_without_images:
                    self.stdout.write(f'  - {reward.abra_code}: {reward.name}')
                    
    def process_images_after_import(self, dataset):
        """
        Process images for imported rewards.
        
        This is a fallback to ensure images are correctly associated, as the after_import_row
        method in the resource class may fail due to timing issues.
        """
        # Target directory for images
        target_dir = os.path.join(settings.MEDIA_ROOT, 'reward_import_images')
        
        # Ensure target directory exists
        if not os.path.exists(target_dir):
            return
            
        # Get the column index for abra_code
        try:
            abra_code_index = dataset.headers.index('abra_code')
        except (ValueError, AttributeError):
            self.stdout.write(self.style.ERROR('Could not find abra_code column in dataset'))
            return
            
        for row in dataset:
            try:
                abra_code = row[abra_code_index]
                if not abra_code:
                    continue
                    
                # Check if image exists
                image_path = os.path.join(target_dir, f"{abra_code}.png")
                if not os.path.exists(image_path):
                    continue
                    
                # Find the reward
                try:
                    reward = Reward.objects.get(abra_code=abra_code)
                    
                    # Skip if already has an image
                    if reward.image:
                        continue
                        
                    # Set the image
                    with open(image_path, 'rb') as img_file:
                        target_filename = f"{abra_code}.png"
                        reward.image.save(
                            target_filename,
                            File(img_file),
                            save=True
                        )
                    self.stdout.write(f'Associated image for {abra_code}')
                except Reward.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f'Reward not found for {abra_code}'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Error setting image for {abra_code}: {e}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error processing row: {e}'))