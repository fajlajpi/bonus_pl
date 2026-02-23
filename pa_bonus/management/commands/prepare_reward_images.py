import os
import csv
import shutil
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from pa_bonus.models import Reward


class Command(BaseCommand):
    help = 'Prepare reward images directory structure and generate CSV mapping file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir', 
            type=str, 
            help='Path where to create the image directory structure',
            default=os.path.join(settings.MEDIA_ROOT, 'reward_images_prep')
        )
        parser.add_argument(
            '--existing-only',
            action='store_true',
            help='Include only rewards that already have images'
        )

    def handle(self, *args, **options):
        output_dir = options['output_dir']
        existing_only = options['existing_only']
        
        # Create the output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # Get all rewards
        if existing_only:
            rewards = Reward.objects.exclude(image='')
        else:
            rewards = Reward.objects.all()
            
        # Create a CSV file to map ABRA codes to reward names
        csv_path = os.path.join(output_dir, 'reward_image_mapping.csv')
        with open(csv_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['abra_code', 'name', 'has_image'])
            
            # Write a row for each reward
            for reward in rewards:
                has_image = bool(reward.image)
                writer.writerow([reward.abra_code, reward.name, 'Yes' if has_image else 'No'])
                
                # If the reward has an image, copy it to the output directory
                if has_image:
                    try:
                        source_path = reward.image.path
                        target_path = os.path.join(output_dir, f"{reward.abra_code}.png")
                        shutil.copy2(source_path, target_path)
                        self.stdout.write(self.style.SUCCESS(
                            f'Copied image for {reward.abra_code} ({reward.name})'
                        ))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(
                            f'Error copying image for {reward.abra_code}: {e}'
                        ))
                else:
                    # Create an empty placeholder file
                    placeholder_path = os.path.join(output_dir, f"{reward.abra_code}.png.placeholder")
                    with open(placeholder_path, 'w') as f:
                        f.write(f"Placeholder for {reward.name}")
                    self.stdout.write(
                        f'Created placeholder for {reward.abra_code} ({reward.name})'
                    )
                    
        self.stdout.write(self.style.SUCCESS(
            f'Created image mapping CSV at {csv_path}\n'
            f'Prepared image files for {rewards.count()} rewards in {output_dir}\n\n'
            f'Next steps:\n'
            f'1. Use the CSV file to identify which rewards need images\n'
            f'2. Replace the placeholder files with actual images\n'
            f'3. Run the import_rewards command to associate the images with rewards'
        ))