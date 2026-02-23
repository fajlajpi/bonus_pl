import os
from django.core.management.base import BaseCommand
from django.core.files import File
from django.conf import settings
from pa_bonus.models import Reward
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Associate images with existing Reward objects without importing any data'

    def add_arguments(self, parser):
        parser.add_argument(
            'image_dir', 
            type=str, 
            help='Path to directory containing images (named as ABRA_CODE.png/jpg/jpeg)'
        )
        parser.add_argument(
            '--target-dir',
            type=str,
            default='reward_images',
            help='Subdirectory in MEDIA_ROOT where images will be stored (default: reward_images)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Replace existing images if they exist'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate the operation without making changes'
        )

    def handle(self, *args, **options):
        image_dir = options['image_dir']
        target_dir = options['target_dir']
        force = options['force']
        dry_run = options['dry_run']

        # Verify the image directory exists
        if not os.path.exists(image_dir):
            self.stderr.write(self.style.ERROR(f'Image directory not found: {image_dir}'))
            return

        # Ensure target directory exists in MEDIA_ROOT
        target_path = os.path.join(settings.MEDIA_ROOT, target_dir)
        if not os.path.exists(target_path) and not dry_run:
            os.makedirs(target_path)
            self.stdout.write(f'Created target directory: {target_path}')

        # Get all image files from the source directory
        image_files = [f for f in os.listdir(image_dir) 
                      if os.path.isfile(os.path.join(image_dir, f)) and 
                      f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        
        self.stdout.write(f'Found {len(image_files)} image files in {image_dir}')
        
        # Statistics counters
        associated_count = 0
        skipped_count = 0
        not_found_count = 0
        error_count = 0
        
        # Associate images with rewards
        for img_file in image_files:
            # Get ABRA code from filename (remove extension)
            abra_code = os.path.splitext(img_file)[0]
            source_path = os.path.join(image_dir, img_file)
            
            try:
                # Find the Reward object by ABRA code
                try:
                    reward = Reward.objects.get(abra_code=abra_code)
                except Reward.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f'No reward found with ABRA code: {abra_code}'))
                    not_found_count += 1
                    continue
                
                # Skip if already has an image and not forcing update
                if reward.image and not force:
                    self.stdout.write(f'Skipping {abra_code}: already has an image (use --force to override)')
                    skipped_count += 1
                    continue
                
                # In dry run mode, just report what would happen
                if dry_run:
                    action = "Would update" if reward.image else "Would associate"
                    self.stdout.write(self.style.SUCCESS(f'{action} image for {abra_code}: {reward.name}'))
                    associated_count += 1
                    continue
                
                # Associate the image with the reward
                with open(source_path, 'rb') as img_file_obj:
                    # Maintain file extension from source
                    _, file_ext = os.path.splitext(source_path)
                    target_filename = f"{abra_code}{file_ext.lower()}"
                    
                    # Save image to the reward
                    reward.image.save(
                        target_filename,
                        File(img_file_obj),
                        save=True
                    )
                
                self.stdout.write(self.style.SUCCESS(f'Associated image for {abra_code}: {reward.name}'))
                associated_count += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error processing {abra_code}: {str(e)}'))
                error_count += 1
        
        # Report final statistics
        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"DRY RUN SUMMARY: Would associate {associated_count} images, "
                f"would skip {skipped_count} existing images, "
                f"{not_found_count} rewards not found, {error_count} errors"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"SUMMARY: Associated {associated_count} images, "
                f"skipped {skipped_count} existing images, "
                f"{not_found_count} rewards not found, {error_count} errors"
            ))
        
        # Additional report of rewards without images
        if not dry_run:
            rewards_without_images = Reward.objects.filter(image='')
            if rewards_without_images.exists():
                self.stdout.write(self.style.WARNING(
                    f'{rewards_without_images.count()} rewards still have no associated image:'
                ))
                for reward in rewards_without_images[:10]:  # Show first 10 only to avoid overwhelming output
                    self.stdout.write(f'  - {reward.abra_code}: {reward.name}')
                
                if rewards_without_images.count() > 10:
                    self.stdout.write(f'  ... and {rewards_without_images.count() - 10} more')