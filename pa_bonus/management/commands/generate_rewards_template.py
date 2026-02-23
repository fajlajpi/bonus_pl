import os
from django.core.management.base import BaseCommand
from django.conf import settings
import pandas as pd
from pa_bonus.models import Brand, Reward


class Command(BaseCommand):
    help = 'Generate an Excel template for rewards import with existing data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output', 
            type=str, 
            help='Path to save the Excel template',
            default=os.path.join(settings.MEDIA_ROOT, 'rewards_import_template.xlsx')
        )
        parser.add_argument(
            '--empty',
            action='store_true',
            help='Generate an empty template instead of including existing rewards'
        )

    def handle(self, *args, **options):
        output_path = options['output']
        empty = options['empty']
        
        # Create the output directory if it doesn't exist
        output_dir = os.path.dirname(output_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Create Excel writer with two sheets
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Sheet 1: Rewards
            if empty:
                # Create an empty template with column headers
                df_rewards = pd.DataFrame(columns=[
                    'abra_code', 'name', 'point_cost', 'description', 'brand', 'is_active'
                ])
                # Add a sample row with clear instructions
                df_rewards.loc[0] = [
                    'ABC123', 
                    'Sample Reward', 
                    1000, 
                    'This is a description of the reward.', 
                    'Brand Name (must exist)',
                    True
                ]
            else:
                # Export all existing rewards
                rewards = Reward.objects.all()
                data = []
                for reward in rewards:
                    data.append({
                        'abra_code': reward.abra_code,
                        'name': reward.name,
                        'point_cost': reward.point_cost,
                        'description': reward.description,
                        'brand': reward.brand.name if reward.brand else '',
                        'is_active': reward.is_active
                    })
                df_rewards = pd.DataFrame(data)
            
            # Write to Excel
            df_rewards.to_excel(writer, sheet_name='Rewards', index=False)
            
            # Sheet 2: Available Brands (for reference)
            brands = Brand.objects.all().values_list('name', flat=True)
            df_brands = pd.DataFrame({'Available Brands': brands})
            df_brands.to_excel(writer, sheet_name='Available Brands', index=False)
            
            # Sheet 3: Instructions
            instructions = [
                ['Rewards Import Template Instructions'],
                [''],
                ['1. Image Convention:'],
                ['   - Images should be named exactly as the ABRA code with .png extension'],
                ['   - Example: For reward with ABRA code "ABC123", the image should be named "ABC123.png"'],
                ['   - Place all images in a single directory when using the import_rewards command'],
                [''],
                ['2. Fields:'],
                ['   - abra_code: Unique identifier for the reward (required)'],
                ['   - name: Name of the reward (required)'],
                ['   - point_cost: Number of points needed to claim the reward (required)'],
                ['   - description: Detailed description of the reward'],
                ['   - brand: Must match an existing brand name in the system. See the "Available Brands" sheet'],
                ['   - is_active: Set to TRUE to make the reward available to users, FALSE to hide it'],
                [''],
                ['3. Import Command:'],
                ['   python manage.py import_rewards rewards_import.xlsx --image-dir=/path/to/images'],
                [''],
                ['4. Preparation:'],
                ['   You can use the prepare_reward_images command to help prepare image files:'],
                ['   python manage.py prepare_reward_images'],
                ['']
            ]
            df_instructions = pd.DataFrame(instructions)
            df_instructions.to_excel(writer, sheet_name='Instructions', header=False, index=False)
        
        self.stdout.write(self.style.SUCCESS(
            f'Successfully generated rewards import template at {output_path}'
        ))