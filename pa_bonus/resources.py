from import_export import resources, fields, widgets
from import_export.widgets import ForeignKeyWidget, ManyToManyWidget
from django.core.files.storage import default_storage
from django.core.files import File
from django.conf import settings
from django.contrib.auth.hashers import make_password
import os
import time
import tablib
import logging
from datetime import datetime
from django.core.exceptions import ValidationError
from .models import Reward, Brand, User, UserContract, UserContractGoal, Region, BrandBonus

logger = logging.getLogger(__name__)

class OptimizedUserResource(resources.ModelResource):
    """
    Optimized import/export settings for the User model.
    
    Compatible with django-import-export 4.3.7
    
    Features:
    - Delayed password hashing for better performance
    - Region lookup optimization
    """
    password = fields.Field(
        column_name='password',
        attribute='password',
    )
    
    region = fields.Field(
        column_name='region',
        attribute='region',
        widget=ForeignKeyWidget(Region, field='code')
    )

    class Meta:
        model = User
        import_id_fields = ['email']
        fields = ('username', 'email', 'first_name', 'last_name', 
                 'user_number', 'user_phone', 'password', 'is_active', 'region')
        batch_size = 100

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cache for regions to avoid repeated DB lookups
        self._region_cache = {}
        # Start time for performance tracking
        self._start_time = None

    def before_import(self, dataset, **kwargs):
        """
        Prepare for import by caching regions and other setup tasks.
        
        In 4.3.7, before_import doesn't receive using_transactions and dry_run.
        """
        self._start_time = time.time()
        
        # Cache all regions for faster lookups
        self._region_cache = {r.code: r for r in Region.objects.all()}
        logger.debug(f"Cached {len(self._region_cache)} regions in {time.time() - self._start_time:.3f}s")
        
        # Let the parent do its thing
        return super().before_import(dataset, **kwargs)

    def before_import_row(self, row, **kwargs):
        """
        Process each row before import.
        
        Ensures all data is properly formatted and that password will be set.
        """
        # Handle empty region values
        if 'region' in row and not row['region']:
            row['region'] = None
        
        # Clean user_number and ensure it's a string
        if 'user_number' in row and row['user_number'] is not None:
            row['user_number'] = str(row['user_number']).strip()
        
        # Clean user_phone and ensure it's a string
        if 'user_phone' in row and row['user_phone'] is not None:
            row['user_phone'] = str(row['user_phone']).strip()
        
        # Most critical part: Always set a password
        # If password is empty in the import, use user_number
        if 'password' not in row or not row['password']:
            if 'user_number' in row and row['user_number']:
                row['password'] = str(row['user_number'])
            elif 'username' in row and row['username']:
                row['password'] = str(row['username'])
            else:
                # Last resort - use a default password
                row['password'] = 'default_password'
        
        # COMMENTED OUT AS WE WERE DOUBLE HASHING, HASHING IS IN SKIP_ROW
        # # Explicitly hash the password here
        # if 'password' in row and row['password']:
        #     row['password'] = make_password(row['password'])
        
        logger.debug(f"Processed row: {row}")

        # Always call the parent method
        super().before_import_row(row, **kwargs)

    def after_import(self, dataset, result, **kwargs):
        """
        Log performance metrics after import.
        
        In 4.3.7, after_import only takes dataset and result as positional args.
        """
        if self._start_time:
            total_time = time.time() - self._start_time
            logger.info(f"User import completed in {total_time:.2f}s - "
                        f"{len(dataset)} rows processed")
        
        return super().after_import(dataset, result, **kwargs)

    def skip_row(self, instance, original, row, import_validation_errors=None, **kwargs):
        """
        Called when we determine if a row should be skipped.
        
        This is a good place to handle password hashing as it's called for every row
        and occurs after validation but before saving.
        """
        # Handle password hashing here, just before the row would be saved
        if 'password' in row and row['password']:
            # Hash the password
            instance.password = make_password(row['password'])
        elif not original and not instance.password:
            # For new users without a specified password, use user_number
            if hasattr(instance, 'user_number') and instance.user_number:
                instance.password = make_password(instance.user_number)
        
        # Call parent implementation to determine if row should be skipped
        return super().skip_row(instance, original, row, import_validation_errors, **kwargs)
    
class UserResource(resources.ModelResource):
    """
    Defines import/export settings for the User model.

    - Can import from XLSX file
    - Hashes passwords
    - Uses email as the primary identifier
    """

    password = fields.Field(
        column_name='password',
        attribute='password',
        widget=None  # We override save_instance to hash passwords
    )
    
    region = fields.Field(
        column_name='region',
        attribute='region',
        widget=widgets.ForeignKeyWidget(Region, field='code')
    )

    class Meta:
        model = User
        import_id_fields = ['email']  # Email is the unique identifier
        fields = ('username', 'email', 'first_name', 'last_name', 'user_number', 'user_phone', 'password', 'is_active', 'region')

    def before_import_row(self, row, **kwargs):
        """
        Automatically sets the default password to user_number and hashes it.
        """
        row['password'] = make_password(str(row['user_number']))
        
        # Handle empty region values
        if 'region' in row and not row['region']:
            row['region'] = None
            
        super().before_import_row(row, **kwargs)


class UserContractResource(resources.ModelResource):
    """
    Defines import/export settings for UserContract.

    - Uses email instead of user_id for better readability in import/export.
    - Automatically fetches the user ID during import.
    """

    user_email = fields.Field(
        column_name='user_email',
        attribute='user_id',
        widget=widgets.ForeignKeyWidget(User, field='email')
    )

    brand_bonuses = fields.Field(
        column_name='brand_bonuses',
        attribute='brandbonuses',
        widget=widgets.ManyToManyWidget(BrandBonus, field='name', separator=', ')
    )

    class Meta:
        model = UserContract
        import_id_fields = ['user_email']  # Use email instead of ID
        fields = ('id', 'user_email', 'contract_date_from', 'contract_date_to', 'is_active', 'brand_bonuses')

    def before_import_row(self, row, **kwargs):
        """
        Ensures that the user exists before importing.
        Automatically assigns the correct user_id based on the email.
        Calls the parent method to retain default behavior.
        """
        super().before_import_row(row, **kwargs)  # Call parent method

        try:
            user = User.objects.get(email=row['user_email'])
            row['user_id'] = user.id  # Assign correct user_id
        except User.DoesNotExist:
            raise ValueError(f"User with email {row['user_email']} does not exist.")

    def after_save_instance(self, instance, new, **kwargs):
        """
        Handles the ManyToMany relationship for BrandBonus after instance creation.

        - Parses the `brand_bonuses` column from the import file.
        - Assigns the corresponding BrandBonus objects to the instance.
        """
        logger.info(f"after_save_instance called with: instance={instance}, new={new}, kwargs={kwargs}")

        if hasattr(instance, 'brandbonuses') and instance.brandbonuses is not None:
            logger.info(f"Processing Brand Bonuses for {instance}")

            # Get the original brand bonuses from the imported row
            row_data = kwargs.get('row', {})
            brand_bonus_names = row_data.get('brand_bonuses', '')

            if brand_bonus_names:
                # Convert the comma-separated string into a list
                bonus_names_list = [name.strip() for name in brand_bonus_names.split(',')]
                logger.info(f"Parsed brand bonuses: {bonus_names_list}")

                # Find matching BrandBonus objects
                bonuses = BrandBonus.objects.filter(name__in=bonus_names_list)
                instance.brandbonuses.set(bonuses)  # Assign ManyToMany relation

class UserContractGoalResource(resources.ModelResource):
    user_email = fields.Field(
        column_name='user_email',
        readonly=True
    )

    contract_date_from = fields.Field(
        column_name='contract_date_from',
        readonly=True
    )

    user_contract = fields.Field(
        column_name='user_contract',
        attribute='user_contract',
        widget=widgets.ForeignKeyWidget(UserContract, field='id')
    )

    brands = fields.Field(
        column_name='brands',
        attribute='brands',
        widget=widgets.ManyToManyWidget(Brand, field='name', separator=',')
    )

    class Meta:
        model = UserContractGoal
        import_id_fields = []  # No natural unique constraint
        fields = (
            'user_email',
            'contract_date_from',
            'user_contract',
            'goal_period_from',
            'goal_period_to',
            'goal_value',
            'goal_base',
            'evaluation_frequency',
            'allow_full_period_recovery',
            'bonus_percentage',
            'brands',
        )
        export_order = fields

    def before_import_row(self, row, **kwargs):
        email = row.get('user_email')
        contract_start = row.get('contract_date_from')

        if not email or not contract_start:
            raise ValidationError("Missing user_email or contract_date_from.")

        # Parse contract_start safely
        try:
            if isinstance(contract_start, str):
                contract_start = contract_start.strip()
                if 'T' in contract_start or 'Z' in contract_start:
                    contract_start = datetime.fromisoformat(contract_start.replace('Z', '+00:00')).date()
                else:
                    contract_start = datetime.strptime(contract_start, "%Y-%m-%d").date()
        except Exception:
            raise ValidationError(f"Invalid date format for contract_date_from: {contract_start}")

        # Find and set user_contract ID
        try:
            contract = UserContract.objects.get(user_id__email=email, contract_date_from=contract_start)
            row['user_contract'] = contract.id
        except UserContract.DoesNotExist:
            raise ValidationError(f"UserContract not found for {email} starting {contract_start}")
        except UserContract.MultipleObjectsReturned:
            raise ValidationError(f"Multiple contracts found for {email} on {contract_start}")

    def skip_row(self, instance, original, row, import_validation_errors=None):
        return not row.get('user_contract')  # skip if lookup failed

class RewardResource(resources.ModelResource):
    """
    Import/Export resource for Reward model.
    
    Handles image file association based on ABRA code.
    """
    abra_code = fields.Field(column_name='abra_code', attribute='abra_code')
    name = fields.Field(column_name='name', attribute='name')
    point_cost = fields.Field(column_name='point_cost', attribute='point_cost')
    description = fields.Field(column_name='description', attribute='description')
    
    # Brand is a ForeignKey, so we use a ForeignKeyWidget
    brand = fields.Field(
        column_name='brand', 
        attribute='brand',
        widget=ForeignKeyWidget(Brand, 'name')
    )
    
    is_active = fields.Field(column_name='is_active', attribute='is_active')
    
    # This field will be used to indicate if an image exists
    image_exists = fields.Field(column_name='image_exists')
    
    class Meta:
        model = Reward
        import_id_fields = ['abra_code']  # abra_code is the unique identifier
        fields = ('abra_code', 'name', 'point_cost', 'description', 'brand', 'is_active', 'image_exists')
        export_order = fields
    
    def before_import_row(self, row, **kwargs):
        """
        Check if an image exists for this reward before importing.
        
        The image should follow the convention: {IMAGES_PATH}/{abra_code}.png
        """
        super().before_import_row(row, **kwargs)
        
        # Handle both dict-like and list-like row objects
        abra_code = None
        
        # If row is dict-like (when using Import-Export admin)
        if hasattr(row, 'get') and callable(row.get):
            if 'abra_code' in row and row['abra_code']:
                abra_code = row['abra_code']
        # If row is list-like (when using Dataset directly)
        elif isinstance(row, (list, tuple)) and kwargs.get('dataset'):
            dataset = kwargs.get('dataset')
            try:
                abra_code_index = dataset.headers.index('abra_code')
                if len(row) > abra_code_index:
                    abra_code = row[abra_code_index]
            except (ValueError, IndexError):
                logger.warning("Could not find abra_code column in dataset")
        
        if abra_code:
            image_path = self._get_image_path(abra_code)
            
            # Add a field to indicate if image exists (for dict-like rows)
            if hasattr(row, '__setitem__'):
                row['image_exists'] = os.path.exists(image_path)
            
            # Log missing images 
            if not os.path.exists(image_path):
                logger.warning(f"No image found for reward {abra_code} at {image_path}")
    
    def after_import_row(self, row, row_result, **kwargs):
        """
        Associate an image with the reward after it has been imported.
        """
        if row_result.import_type != 'skip' and row.get('image_exists'):
            # Get the ABRA code directly from the row
            abra_code = row.get('abra_code')
            if not abra_code:
                return
                
            # Find the reward instance by ABRA code
            try:
                instance = Reward.objects.get(abra_code=abra_code)
                
                # Set the image
                image_path = self._get_image_path(abra_code)
                self._set_reward_image(instance, image_path)
            except Reward.DoesNotExist:
                logger.error(f"Reward with ABRA code {abra_code} not found after import")
            except Exception as e:
                logger.error(f"Error setting image for {abra_code}: {str(e)}")
    
    def dehydrate_image_exists(self, reward):
        """
        Prepare the image_exists field for export.
        """
        return bool(reward.image)
    
    def _get_image_path(self, abra_code):
        """
        Get the expected image path for a given ABRA code.
        
        Args:
            abra_code: The ABRA code of the reward.
            
        Returns:
            str: Path to the expected image file.
        """
        # Use a subdirectory 'reward_import_images' in MEDIA_ROOT
        import_dir = os.path.join(settings.MEDIA_ROOT, 'reward_import_images')
        
        # Make sure the directory exists
        if not os.path.exists(import_dir):
            os.makedirs(import_dir)
            
        # Return the path to the image file
        return os.path.join(import_dir, f"{abra_code}.png")
    
    def _set_reward_image(self, reward, image_path):
        """
        Set the image for a reward based on the image_path.
        
        Args:
            reward: The Reward instance.
            image_path: Path to the image file.
        """
        if not os.path.exists(image_path):
            return
            
        try:
            with open(image_path, 'rb') as img_file:
                # The target path in the media directory
                target_filename = f"{reward.abra_code}.png"
                
                # Set the image field
                reward.image.save(
                    target_filename,
                    File(img_file),
                    save=True
                )
                
            logger.info(f"Successfully associated image for reward {reward.abra_code}")
        except Exception as e:
            logger.error(f"Error setting image for reward {reward.abra_code}: {e}")