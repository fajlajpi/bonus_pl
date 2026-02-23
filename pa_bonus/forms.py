from django import forms
from .models import FileUpload
from django.db import transaction
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from pa_bonus.models import (
    User, UserContract, UserContractGoal, Brand, BrandBonus, Region,
    Invoice, InvoiceBrandTurnover, PointsTransaction
)
import datetime
from decimal import Decimal

import logging

logger = logging.getLogger(__name__)


class FileUploadForm(forms.ModelForm):
    class Meta:
        model = FileUpload
        fields = ['file']

    def clean_file(self):
        file = self.cleaned_data['file']

        # Check file extension
        ext = file.name.split('.')[-1].lower()
        if ext not in ['xls','xlsx', 'csv']:
            raise forms.ValidationError('Unsupported filetype')
        
        # Check file size (limit 15 MB)
        if file.size > 15 * 1024 * 1024:
            raise forms.ValidationError('File too large (>15 MB)')
        
        return file
    
class EmailAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="Email nebo uživatelské jméno",
        widget=forms.TextInput(attrs={'autofocus': True}),
    )
    password = forms.CharField(
        label="Heslo",
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
    )
    
    error_messages = {
        'invalid_login': "Zadejte prosím správné uživatelské jméno (nebo emailovou adresu) a heslo. ",
        'inactive': "Tento účet je neaktivní.",
    }

class ClientCreationForm(forms.Form):
    """
    Comprehensive form for creating a client with contract, optional goal,
    and optional retroactive transaction processing.
    """
    
    # ========== USER FIELDS ==========
    username = forms.CharField(
        max_length=150,
        label='Username',
        help_text='Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    email = forms.EmailField(
        label='Email',
        help_text='Required. Will be used for login and notifications.',
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    
    first_name = forms.CharField(
        max_length=150,
        label='First Name',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    last_name = forms.CharField(
        max_length=150,
        label='Last Name',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    user_number = forms.CharField(
        max_length=20,
        label='Customer Number (Zákaznické číslo)',
        help_text='Required. Must be unique. This will also be the default password.',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    user_phone = forms.CharField(
        max_length=10,
        label='Phone Number',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    region = forms.ModelChoiceField(
        queryset=Region.objects.filter(is_active=True),
        label='Region',
        required=False,
        empty_label='Select Region',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    is_active = forms.BooleanField(
        initial=True,
        required=False,
        label='Active User',
        help_text='User can log in and use the system',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    # ========== CONTRACT FIELDS ==========
    contract_date_from = forms.DateField(
        label='Contract Start Date',
        help_text='Required. Format: YYYY-MM-DD',
        initial=datetime.date.today,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    
    contract_date_to = forms.DateField(
        label='Contract End Date',
        help_text='Required. Format: YYYY-MM-DD',
        initial=lambda: datetime.date.today() + datetime.timedelta(days=365),
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    
    contract_is_active = forms.BooleanField(
        initial=True,
        required=False,
        label='Active Contract',
        help_text='Contract is currently active',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    brand_bonuses = forms.ModelMultipleChoiceField(
        queryset=BrandBonus.objects.all(),
        label='Brand Bonuses',
        required=False,
        help_text='Select applicable brand bonus schemes for this contract',
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': '5'})
    )
    
    # ========== GOAL FIELDS (OPTIONAL) ==========
    create_goal = forms.BooleanField(
        initial=False,
        required=False,
        label='Create Contract Goal',
        help_text='Check to add an initial contract goal',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_create_goal'})
    )
    
    goal_brands = forms.ModelMultipleChoiceField(
        queryset=Brand.objects.all(),
        label='Goal Brands',
        required=False,
        help_text='Brands included in this goal',
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': '5'})
    )
    
    goal_period_from = forms.DateField(
        label='Goal Period Start',
        required=False,
        help_text='Start date for this goal period',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    
    goal_period_to = forms.DateField(
        label='Goal Period End',
        required=False,
        help_text='End date for this goal period',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    
    goal_value = forms.IntegerField(
        label='Target Turnover',
        required=False,
        help_text='Target turnover for the entire period',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0'})
    )
    
    goal_base = forms.IntegerField(
        label='Baseline Turnover',
        required=False,
        help_text='Historical baseline for comparison',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0'})
    )
    
    evaluation_frequency = forms.IntegerField(
        initial=6,
        label='Evaluation Frequency (months)',
        required=False,
        help_text='How often to evaluate progress in months',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '12'})
    )
    
    allow_full_period_recovery = forms.BooleanField(
        initial=True,
        required=False,
        label='Allow Full Period Recovery',
        help_text='Missing early milestones can be recovered if full period goal is met',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    bonus_percentage = forms.FloatField(
        initial=0.5,
        label='Bonus Percentage',
        required=False,
        help_text='Percentage of exceeded amount to award as points (0.5 = 50%)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'max': '1', 'step': '0.01'})
    )
    
    # ========== RETROACTIVE TRANSACTION PROCESSING ==========
    process_historical_transactions = forms.BooleanField(
        initial=False,
        required=False,
        label='Process Historical Transactions',
        help_text='Automatically create transactions for existing invoices within the contract period',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_process_historical'})
    )
    
    def clean_username(self):
        """Validate that username is unique."""
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise ValidationError('A user with this username already exists.')
        return username
    
    def clean_email(self):
        """Validate that email is unique."""
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError('A user with this email already exists.')
        return email
    
    def clean_user_number(self):
        """Validate that user_number is unique."""
        user_number = self.cleaned_data.get('user_number')
        if User.objects.filter(user_number=user_number).exists():
            raise ValidationError('A user with this customer number already exists.')
        return user_number
    
    def clean(self):
        """Perform cross-field validation."""
        cleaned_data = super().clean()
        
        # Validate contract dates
        contract_from = cleaned_data.get('contract_date_from')
        contract_to = cleaned_data.get('contract_date_to')
        
        if contract_from and contract_to:
            if contract_to <= contract_from:
                raise ValidationError('Contract end date must be after start date.')
        
        # Validate goal fields if goal creation is requested
        create_goal = cleaned_data.get('create_goal')
        if create_goal:
            goal_brands = cleaned_data.get('goal_brands')
            goal_from = cleaned_data.get('goal_period_from')
            goal_to = cleaned_data.get('goal_period_to')
            goal_value = cleaned_data.get('goal_value')
            goal_base = cleaned_data.get('goal_base')
            
            if not goal_brands:
                self.add_error('goal_brands', 'Brands are required when creating a goal.')
            
            if not goal_from:
                self.add_error('goal_period_from', 'Goal start date is required when creating a goal.')
            
            if not goal_to:
                self.add_error('goal_period_to', 'Goal end date is required when creating a goal.')
            
            if goal_value is None:
                self.add_error('goal_value', 'Target turnover is required when creating a goal.')
            
            if goal_base is None:
                self.add_error('goal_base', 'Baseline turnover is required when creating a goal.')
            
            if goal_from and goal_to:
                if goal_to <= goal_from:
                    raise ValidationError('Goal end date must be after start date.')
                
                if contract_from and goal_from < contract_from:
                    self.add_error('goal_period_from', 
                                 'Goal start date must be within contract period.')
                
                if contract_to and goal_to > contract_to:
                    self.add_error('goal_period_to', 
                                 'Goal end date must be within contract period.')
        
        return cleaned_data
    
    def _process_retroactive_transactions(self, user, contract):
        """
        Process historical invoices and create transactions for this new client.
        
        This method:
        1. Finds all invoices matching the user's user_number
        2. Filters to invoices within the contract period
        3. Creates PointsTransaction records for invoice brand turnovers
        4. Uses the contract's brand bonuses to calculate points
        5. Checks for existing transactions to avoid duplicates
        
        Returns:
            dict: Statistics about transactions created
        """
        stats = {
            'invoices_found': 0,
            'invoices_processed': 0,
            'transactions_created': 0,
            'transactions_skipped': 0,
            'brands_without_bonus': 0,
            'errors': []
        }
        
        # Get all invoices for this client within the contract period
        invoices = Invoice.objects.filter(
            client_number=user.user_number,
            invoice_date__gte=contract.contract_date_from,
            invoice_date__lte=contract.contract_date_to
        ).prefetch_related('brand_turnovers')
        
        stats['invoices_found'] = invoices.count()
        logger.info(f"Found {stats['invoices_found']} historical invoices for user {user.user_number}")
        
        if stats['invoices_found'] == 0:
            return stats
        
        # Get brand bonuses for this contract
        brand_bonuses = {bb.brand_id: bb for bb in contract.brandbonuses.all()}
        
        if not brand_bonuses:
            logger.warning(f"No brand bonuses found for contract {contract.id}")
            stats['errors'].append('No brand bonuses configured for this contract')
            return stats
        
        # Process each invoice
        for invoice in invoices:
            try:
                transactions_for_this_invoice = 0
                
                # Process each brand turnover for this invoice
                for turnover in invoice.brand_turnovers.all():
                    # Check if this brand has a bonus scheme in the contract
                    if turnover.brand not in brand_bonuses:
                        stats['brands_without_bonus'] += 1
                        logger.debug(
                            f"Skipping brand {turnover.brand.name} on invoice {invoice.invoice_number} "
                            f"- no bonus scheme in contract"
                        )
                        continue
                    
                    brand_bonus = brand_bonuses[turnover.brand]
                    
                    # Check if transaction already exists
                    existing_transaction = PointsTransaction.objects.filter(
                        user=user,
                        invoice=invoice,
                        brand=turnover.brand
                    ).exists()
                    
                    if existing_transaction:
                        stats['transactions_skipped'] += 1
                        logger.debug(
                            f"Skipping duplicate transaction for invoice {invoice.invoice_number}, "
                            f"brand {turnover.brand.name}"
                        )
                        continue
                    
                    # Calculate points based on brand bonus ratio
                    # Convert points_ratio to Decimal to avoid type mismatch
                    points = int(turnover.amount * Decimal(str(brand_bonus.points_ratio)))
                    
                    # Determine transaction type and status based on invoice type
                    # Match the existing system's logic from tasks.py
                    if invoice.invoice_type == 'INVOICE':
                        transaction_type = 'STANDARD_POINTS'
                        status = 'PENDING'
                    else:  # CREDIT_NOTE
                        transaction_type = 'CREDIT_NOTE_ADJUST'
                        status = 'CONFIRMED'
                        points = -points  # Negative for credit notes
                    
                    # Create the transaction
                    PointsTransaction.objects.create(
                        user=user,
                        value=points,
                        date=invoice.invoice_date,
                        description=f"Invoice {invoice.invoice_number}",
                        type=transaction_type,
                        status=status,
                        brand=turnover.brand,
                        invoice=invoice
                    )
                    
                    stats['transactions_created'] += 1
                    transactions_for_this_invoice += 1
                
                # Count invoice as processed regardless of whether transactions were created
                # This gives better visibility into what was examined
                stats['invoices_processed'] += 1
                
                if transactions_for_this_invoice > 0:
                    logger.debug(
                        f"Processed invoice {invoice.invoice_number}: "
                        f"created {transactions_for_this_invoice} transaction(s)"
                    )
                else:
                    logger.info(
                        f"Invoice {invoice.invoice_number} processed but no transactions created "
                        f"(no brands with bonus schemes)"
                    )
                    
            except Exception as e:
                error_msg = f"Error processing invoice {invoice.invoice_number}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                stats['errors'].append(error_msg)
        
        logger.info(
            f"Retroactive processing complete for user {user.user_number}: "
            f"{stats['transactions_created']} transactions created, "
            f"{stats['transactions_skipped']} skipped"
        )
        
        return stats
    
    def save(self):
        """
        Create User, UserContract, UserContractGoal, and optionally process
        historical transactions.
        
        Returns:
            tuple: (User instance, transaction stats dict or None)
        """
        with transaction.atomic():
            # Create User
            user = User.objects.create(
                username=self.cleaned_data['username'],
                email=self.cleaned_data['email'],
                first_name=self.cleaned_data['first_name'],
                last_name=self.cleaned_data['last_name'],
                user_number=self.cleaned_data['user_number'],
                user_phone=self.cleaned_data.get('user_phone', ''),
                region=self.cleaned_data.get('region'),
                is_active=self.cleaned_data.get('is_active', True),
                password=make_password(self.cleaned_data['user_number'])
            )
            
            # Create UserContract
            contract = UserContract.objects.create(
                user_id=user,
                contract_date_from=self.cleaned_data['contract_date_from'],
                contract_date_to=self.cleaned_data['contract_date_to'],
                is_active=self.cleaned_data.get('contract_is_active', True)
            )
            
            # Add brand bonuses to contract
            if self.cleaned_data.get('brand_bonuses'):
                contract.brandbonuses.set(self.cleaned_data['brand_bonuses'])
            
            # Create UserContractGoal if requested
            if self.cleaned_data.get('create_goal'):
                goal = UserContractGoal.objects.create(
                    user_contract=contract,
                    goal_period_from=self.cleaned_data['goal_period_from'],
                    goal_period_to=self.cleaned_data['goal_period_to'],
                    goal_value=self.cleaned_data['goal_value'],
                    goal_base=self.cleaned_data['goal_base'],
                    evaluation_frequency=self.cleaned_data.get('evaluation_frequency', 6),
                    allow_full_period_recovery=self.cleaned_data.get('allow_full_period_recovery', True),
                    bonus_percentage=self.cleaned_data.get('bonus_percentage', 0.5)
                )
                
                if self.cleaned_data.get('goal_brands'):
                    goal.brands.set(self.cleaned_data['goal_brands'])
            
            # Process historical transactions if requested
            transaction_stats = None
            if self.cleaned_data.get('process_historical_transactions'):
                transaction_stats = self._process_retroactive_transactions(user, contract)
        
        return user, transaction_stats
