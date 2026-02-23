from django.db import models
from django.db.models import Sum
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.contrib.contenttypes.models import ContentType
import os
import logging

# Configure logger
logger = logging.getLogger(__name__)

# Utility function
def get_upload_path(instance, filename) -> str:
    """
    Returns path to upload files to in the form of MEDIA_ROOT/uploads/YYYY/MM/DD/filename.

    Returns:
        str: Path to upload file
    """
    # Files will me uploaded to MEDIA_ROOT/uploads/YYYY/MM/DD/
    return os.path.join(
        'uploads',
        instance.uploaded_at.strftime('%Y/%d/%d'),
        filename
    )

class Region(models.Model):
    """
    Represents a sales region or territory.
    
    Attributes:
        name (str): The name of the region (max 50 characters)
        code (str): A short code for the region (max 10 characters)
        description (str): Optional description of the region
        is_active (bool): Whether the region is currently active
        created_at (DateTime): When this region was created
    """
    name = models.CharField(max_length=50, unique=True)
    code = models.CharField(max_length=10, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name

class RegionRep(models.Model):
    """
    Join table linking Sales Representatives to Regions.
    
    This model allows tracking which Sales Reps are responsible for which regions,
    including historical assignments.
    
    Attributes:
        user (User): The Sales Rep (User must be in 'Sales Reps' group)
        region (Region): The region this Sales Rep is assigned to
        is_primary (bool): Whether this Rep is the primary representative for the region
        date_from (Date): When this assignment began
        date_to (Date): When this assignment ended (null for current assignments)
        is_active (bool): Whether this assignment is currently active
    """
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='region_assignments')
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name='assigned_reps')
    is_primary = models.BooleanField(default=True)
    date_from = models.DateField()
    date_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-date_from']
        unique_together = [
            # Ensure a user can't be assigned to the same region twice in active status
            ('user', 'region', 'is_active'),
            # Only one primary rep per region when active
            ('region', 'is_primary', 'is_active'),
        ]
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.region.name} ({self.date_from})"
    
    def clean(self):
        """
        Custom validation to ensure the User is in the 'Sales Reps' group.
        """
        from django.core.exceptions import ValidationError
        if not self.user.groups.filter(name='Sales Reps').exists():
            raise ValidationError({'user': 'User must be in the Sales Reps group'})
        
        # Ensure date_to is after date_from if provided
        if self.date_to and self.date_to < self.date_from:
            raise ValidationError({'date_to': 'End date must be after start date'})
        
        super().clean()
    
    def save(self, *args, **kwargs):
        """
        Override save to ensure validation is called.
        """
        self.clean()
        super().save(*args, **kwargs)

class User(AbstractUser):
    """
    Represents a user in the bonus system.

    This model saves a user in the bonus system. A user can be a client, or can
    belong to a group Managers and be staff.

    Attributes:
        username (str): The username to login with (max 150 characters)
        first_name (str): First name (max 150 characters)
        last_name (str): Last name (max 150 characters)
        email (str): Email address
        is_staff (bool): Whether the user is a staff member and can access admin
        is_active (bool): Whether the user is active, to be used instead of deleting
        date_joined (DateTime): The datetime of the user joining
        
        user_number (str): The Customer Number (Zákaznické číslo) from ERP. Can be alphanumeric.
        user_phone (str): The Customer phone number (max 10 characters)
        region (Region): The sales region this client belongs to (for clients only)
    """
    user_number = models.CharField(max_length=20, unique=True)
    user_phone = models.CharField(max_length=10, unique=False)
    region = models.ForeignKey(Region, null=True, blank=True, on_delete=models.SET_NULL, 
                              related_name='clients')

    def __str__(self):
        return self.username + ' | ' + (self.first_name + ' ' + self.last_name if self.first_name or self.last_name else '')

    def get_balance(self) -> int:
        """
        Returns the customers current point balance.

        Returns:
            int: Current point balance, 0 if there are no transactions
        """
        total_points = PointsTransaction.objects.filter(
            user = self.id,
            status = 'CONFIRMED'
        ).aggregate(
            total = Sum('value')
        )
        return total_points['total'] if total_points['total'] is not None else 0
    
    def get_sales_rep(self):
        """
        Returns the primary Sales Rep for this client's region.
        
        Returns:
            User: The primary Sales Rep user, or None if no region or no rep assigned
        """
        if not self.region:
            return None
        
        # Get the active primary rep for this region
        rep_assignment = RegionRep.objects.filter(
            region=self.region, 
            is_active=True,
            is_primary=True
        ).first()
        
        return rep_assignment.user if rep_assignment else None

class UserActivity(models.Model):
    """
    Tracks user login and site activity.
    
    Attributes:
        user (User): The user being tracked
        date (Date): The date of activity
        last_activity (DateTime): Timestamp of the last activity
        visit_count (int): Number of visits/page loads for this day
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    last_activity = models.DateTimeField()
    visit_count = models.IntegerField(default=1)
    
    class Meta:
        unique_together = ['user', 'date']
        ordering = ['-date', 'user']
        
    def __str__(self):
        return f"{self.user} - {self.date} ({self.visit_count} visits)"

class Brand(models.Model):
    """
    Represents a brand. Needed for BrandBonuses, and also for processing invoices using the brand prefix.

    Attributes:
        name (str): The name of the brand (max 50 characters)
        prefix (str): The prefix of the brand in the ABRA ERP (Commonly 1-3 characters, max 10 characters)
    """
    name = models.CharField(max_length=50)
    prefix = models.CharField(max_length=10)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class UserContract(models.Model):
    """
    Represents a contract the User has within the bonus system.

    Attributes:
        user_id (User): The User object the UserContract belongs to.
        contract_date_from (DateField): The start date of the contract.
        contract_date_to (DateField): The end date of the contract.
        is_active (bool): Whether the contract is active or not.
        brandbonuses (BrandBonus): Each contract has one or more BrandBonuses relating to it which determine ho to add points
    """
    user_id = models.ForeignKey(User, on_delete=models.CASCADE)
    contract_date_from = models.DateField()
    contract_date_to = models.DateField()
    is_active = models.BooleanField(default=True)
    brandbonuses = models.ManyToManyField('BrandBonus', related_name="user_contract")

    class Meta:
        ordering = ['-contract_date_from']

    def __str__(self):
        user_name = self.user_id.last_name + ' ' + self.user_id.first_name

        return user_name + f' ({self.contract_date_from})'

class PointsTransaction(models.Model):
    """
    Represents one points transaction in the system.

    The model represents one transaction in the system. The transactions are to be created monthly,
    always for the past month. They are granulated to the invoice and brand, so for each brand
    on each invoice, there is one transaction adding points.
    There can be points deducted (negative value) for claiming rewards or for Credit Notes (which
    are opposites of invoices).

    Attributes:
        value (int): The point value of the transaction.
        date (Date): The date the transaction was recorded.
        user (User): The User object the transaction belongs to.
        description (str): A description of the transaction (max 100 characters).
        type (str): Type of the transaction.
        status (str): Current status of the transaction.
        brand (Brand): Brand the transaction relates to (optional).
        invoice (Invoice): Invoice the transaction relates to (optional).
        reward_request (RewardRequest): The reward request the transaction relates to (optional).
        created_at (DateTime): The datetime the transaction was created.

    """
    TRANSACTION_TYPES = (
        ('STANDARD_POINTS', 'Standard Points added'),
        ('REWARD_CLAIM', 'Reward Claim'),
        ('CREDIT_NOTE_ADJUST', 'Credit Note (dobropis) adjustment'),
        ('ADJUSTMENT', 'Manual Adjustment'),
    )
    TRANSACTION_STATUS = (
        ('NO-CONTRACT', 'No-Contract'),
        ('PENDING', 'Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('CANCELLED', 'Cancelled')
    )
    value = models.IntegerField()
    date = models.DateField()
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    description = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    status = models.CharField(max_length=20, choices=TRANSACTION_STATUS)
    brand = models.ForeignKey(Brand, null=True, blank=True, on_delete=models.SET_NULL)
    invoice = models.ForeignKey('Invoice', null=True, blank=True, on_delete=models.SET_NULL)
    reward_request = models.ForeignKey('RewardRequest', null=True, blank=True, on_delete=models.CASCADE)
    file_upload = models.ForeignKey('FileUpload', null=True, blank=True, on_delete=models.CASCADE, related_name='Transactions')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
    
    def __str__(self):
        return f'{self.user} | {self.date} | {self.type} | {self.value}'

class PointsBalance(models.Model):
    """
    Represents a current points balance for the user. Currently not implemented. The idea
    is caching the balance to avoid counting it every time, but that likely won't be needed
    anytime soon.

    Attributes:
        user_id (User): The user this balance belongs to
        date (Date): Date this balance was calculated
        points (int): The balance of points
    """
    user_id = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    points = models.IntegerField()

class BrandBonus(models.Model):
    """
    Represents a ratio for adding bonus points for turnover in a brand.

    Attributes:
        name (str): Name of the bonus for clarity (max 100 characters).
        points_ratio (float): Ratio of points to turnover, e.g. 0.5 means for 10 CZK turnover give 5 points
        brand_id (Brand): The brand this bonus relates to. Needed to get the brand prefix.
    """
    name = models.CharField(max_length=100)
    points_ratio = models.FloatField()
    brand_id = models.ForeignKey(Brand, on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.name} | {self.brand_id} | {self.points_ratio} points per '

class FileUpload(models.Model):
    """
    Represents an uploaded file with invoice data. Includes a special permission can_manage.

    Attributes:
        file (File): The uploaded file.
        uploaded_at (DateTime): The datetime the file was uploaded.
        processed_at (DateTime): The datetime the file was processed.
        status (str): Current status of the uploaded file's processing.
        error_message (str): Any error messages encountered while processing.
        uploaded_by (User): The User object the file was uploaded by.
    """
    PROCESSING_STATUS = (
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    )
    file = models.FileField(upload_to="uploads/%Y/%m/%d/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=PROCESSING_STATUS, default='PENDING')
    error_message = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    processed_rows = models.IntegerField(default=0)
    total_rows = models.IntegerField(default=0)

    class Meta:
        ordering = ['-uploaded_at']
        permissions = [
            ('can_manage', 'Can manage file uploads')
        ]

    def __str__(self):
        return f'Upload {self.id} | {self.uploaded_at} | {self.status} | by {self.uploaded_by}'
    
class Reward(models.Model):
    """
    Represents a reward item the Clients can claim for their points.

    Attributes:
        abra_code (str): Code in the ABRA system for the item (max 30 characters)
        name (str): Name of the item (max 100 characters)
        point_cost (int): Point cost of the item.
        description (str): Description of the item.
        brand (Brand): Brand, in case the item is restricted to only clients with the same Brand in their UserContract (optional)
        in_showcase (bool): Whether the item should be displayed in the public catalogue showcase.
        is_active (bool): Whether the item is active.
        image (Image): Image representing the item.
        created_at (DateTime): The datetime the item was created.
    """
    AVAILABILITY_TYPE = (
        ('AVAILABLE', 'Available'),
        ('AVAILABLE_LAST_UNITS', 'Available (Last units)'),
        ('ON_DEMAND', 'On Demand'),
        ('UNAVAILABLE', 'Unavailable'),
    )
    abra_code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    point_cost = models.IntegerField()
    description = models.TextField()
    availability = models.CharField(max_length=20, choices=AVAILABILITY_TYPE, default='ON_DEMAND')
    brand = models.ForeignKey(Brand, null=True, blank=True, on_delete=models.SET_NULL)
    is_active = models.BooleanField(default=True)
    in_showcase = models.BooleanField(default=False, help_text="Display this item in the public showcase")
    image = models.ImageField(upload_to='reward_images/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.brand.prefix if self.brand is not None else 'no brand'} | {self.name}'
    
    class Meta:
        ordering = ['abra_code']

class RewardRequest(models.Model):
    """
    Represents a User's request for reward redemption.

    Attributes:
        user (User): The user this request belongs to.
        requested_at (DateTime): The time the request was created.
        status (str): Current status of the request.
        description (str): Description of the request, especially for rejected / cancelled ones.
        total_points (int): The total point value of the request.
    """
    REQUEST_STATUS = (
        ('DRAFT', 'Draft'),
        ('PENDING', 'Pending'),
        ('ACCEPTED', 'Accepted'),
        ('REJECTED', 'Rejected'),
        ('FINISHED', 'Finished'),
        ('CANCELLED', 'Cancelled'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    requested_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=REQUEST_STATUS, default='DRAFT')
    description = models.TextField()
    total_points = models.IntegerField(default=0)
    note = models.TextField(blank=True, null=True, verbose_name="Customer Note")
    indexes = [
        models.Index(fields=['status', '-requested_at']),
        models.Index(fields=['user', '-requested_at']),
        models.Index(fields=['requested_at']),
    ]

    def __str__(self):
        return f"Request {self.id} | by {self.user} | on {self.requested_at.strftime('%Y-%m-%d')} | TOTAL: {self.total_points} pts"

    def save(self, *args, **kwargs):
        """
        Additionally calculates total point value of the items in the request to save.
        """
        # When saving to model, save the total points 
        try:
            self.total_points = sum(item.quantity * item.point_cost for item in self.rewardrequestitem_set.all())
        except ValueError:
            self.total_points = 0
        super().save(*args, **kwargs)

class RewardRequestItem(models.Model):
    """
    Represents an element of a RewardRequest - a Reward, its quantity and point cost at the time of request.

    Attributes:
        reward_request (RewardRequest): The RewardRequest this item belongs to.
        reward (Reward): The item requested.
        quantity (int): The quantity of items requested.
        point_cost (int): The point cost at the time of request.
    """
    reward_request = models.ForeignKey(RewardRequest, on_delete=models.CASCADE)
    reward = models.ForeignKey(Reward, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    point_cost = models.IntegerField()  # Storing point cost at the time of request, in case it changes over time

    def __str__(self):
        return f"{self.quantity} x {self.reward.name} | {self.reward_request}"
    
    def save(self, *args, **kwargs):
        """
        Save with the current point cost in case it changes in the meantime.
        """
        #Set point cost from Reward before saving.
        self.point_cost = self.reward.point_cost
        super().save(*args, **kwargs)

class EmailNotification(models.Model):
    NOTIFICATION_STATUS = (
        ('PENDING', 'Pending'),
        ('SENT', 'Sent'),
        ('FAILED', 'Failed'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    subject = models.CharField(max_length=255)
    message = models.TextField()
    status = models.CharField(max_length=10, choices=NOTIFICATION_STATUS, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.subject} to {self.user.email} ({self.status})"
    
# Utility function to create group and permissions
def create_manager_group_and_permissions(*args, **options):
    """
    Creates the 'Managers' group and assigns the 'can_manage' permission.
    This function should be called after migrations, like in a data migration.
    """
    try:
        #Create group
        manager_group, created = Group.objects.get_or_create(name='Managers')
        logger.info("Manager group created/retrieved")

        #Get permission object
        content_type = ContentType.objects.get_for_model(FileUpload)
        can_manage_perm = Permission.objects.get(
            codename='can_manage',
            content_type=content_type,
        )
        logger.info("Can manage permission retrieved")

        #Add permission to group
        manager_group.permissions.add(can_manage_perm)
        logger.info("Can manage permission assigned to Manager group")

        print("Manager group and permissions setup successfully")
    except Exception as e:
        logger.error(f"Error creating Manager group and permissions: {e}", exc_info=True)
        print(f"Error creating Manager group and permissions: {e}")

class Invoice(models.Model):
    """
    Represents an invoice from the accounting system.
    
    This model stores the base information about invoices imported from the 
    accounting system, regardless of whether the client is registered in the
    bonus program.
    
    Attributes:
        invoice_number (str): The unique invoice number.
        client_number (str): The client's number in the accounting system.
        invoice_date (Date): The date of the invoice.
        total_amount (Decimal): The total amount of the invoice.
        invoice_type (str): Type of invoice (standard invoice or credit note).
        file_upload (FileUpload): The file upload that created this invoice.
        created_at (DateTime): When this record was created.
    """
    INVOICE_TYPES = (
        ('INVOICE', 'Standard Invoice'),
        ('CREDIT_NOTE', 'Credit Note'),
    )
    
    invoice_number = models.CharField(max_length=50, unique=True)
    client_number = models.CharField(max_length=20, db_index=True)
    invoice_date = models.DateField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    invoice_type = models.CharField(max_length=15, choices=INVOICE_TYPES)
    file_upload = models.ForeignKey('FileUpload', on_delete=models.CASCADE, 
                                   related_name='invoices')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-invoice_date', 'invoice_number']
        indexes = [
            models.Index(fields=['client_number', 'invoice_date']),
        ]
    
    def __str__(self):
        return f"{self.invoice_number} | {self.client_number} | {self.invoice_date}"


class InvoiceBrandTurnover(models.Model):
    """
    Represents the turnover for a specific brand within an invoice.
    
    Attributes:
        invoice (Invoice): The invoice this turnover belongs to.
        brand (Brand): The brand this turnover is for.
        amount (Decimal): The total amount for this brand in the invoice.
    """
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, 
                               related_name='brand_turnovers')
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE,
                             related_name='invoice_turnovers')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    class Meta:
        unique_together = ['invoice', 'brand']
        ordering = ['-invoice__invoice_date', 'brand__name']
    
    def __str__(self):
        return f"{self.invoice.invoice_number} | {self.brand.name} | {self.amount}"

