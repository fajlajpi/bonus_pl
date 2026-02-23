import logging
from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.admin.widgets import FilteredSelectMultiple, AdminDateWidget
from import_export import resources, fields, widgets
from import_export.widgets import DateWidget
from import_export.admin import ExportMixin, ImportExportMixin
from django.forms.models import BaseInlineFormSet
from pa_bonus.models import (
    User, Brand, UserContract, UserContractGoal, PointsTransaction, BrandBonus, 
    FileUpload, Reward, RewardRequest, RewardRequestItem, EmailNotification, Invoice, InvoiceBrandTurnover,
    Region, RegionRep, UserActivity, GoalEvaluation, 
)
from .resources import UserResource, UserContractResource, UserContractGoalResource, RewardResource, OptimizedUserResource


logger = logging.getLogger(__name__)

# INLINE FORMS
class UserContractGoalInlineForm(forms.ModelForm):
    class Meta:
        model = UserContractGoal
        fields = '__all__'
        widgets = {
            'goal_period_from': AdminDateWidget(),
            'goal_period_to': AdminDateWidget(),
            'brands': FilteredSelectMultiple("Brands", is_stacked=False),
        }

# INLINES
class RewardRequestItemInline(admin.TabularInline):
    model = RewardRequestItem
    extra = 1  # Number of empty forms shown

class UserContractInlineFormSet(BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        kwargs['initial'] = [
            {'contract_date_from': '2025-01-01', 'contract_date_to': '2025-12-31'}
        ]
        super(UserContractInlineFormSet, self).__init__(*args, **kwargs)

class UserContractInline(admin.TabularInline):
    model = UserContract
    extra = 0  # Number of empty forms shown
    formset = UserContractInlineFormSet

class UserContractGoalInline(admin.TabularInline):
    model = UserContractGoal
    fk_name = "user_contract"
    form = UserContractGoalInlineForm
    extra = 0

class InvoiceBrandTurnoverInline(admin.TabularInline):
    model = InvoiceBrandTurnover
    extra = 0
    

# CUSTOM ACTIONS
def approve_requests(modeladmin, request, queryset):
    queryset.update(status='ACCEPTED')

def reject_requests(modeladmin, request, queryset):
    queryset.update(status='REJECTED')

def confirm_transactions(modeladmin, request, queryset):
    queryset.update(status='CONFIRMED')

def pending_transactions(modeladmin, request, queryset):
    queryset.update(status='PENDING')

def cancel_transactions(modeladmin, request, queryset):
    queryset.update(status='CANCELLED')

def reward_availability_set_available(modeladmin, request, queryset):
    queryset.update(availability='AVAILABLE')

def reward_availability_set_on_demand(modeladmin, request, queryset):
    queryset.update(availability='ON_DEMAND')

def reward_availability_set_unavailable(modeladmin, request, queryset):
    queryset.update(availability='UNAVAILABLE')

def reward_set_active(modeladmin, request, queryset):
    queryset.update(is_active=True)

def reward_set_inactive(modeladmin, request, queryset):
    queryset.update(is_active=False)




approve_requests.short_description = "Approve selected requests"
reject_requests.short_description = "Reject selected requests"
confirm_transactions.short_description = "Confirm selected transactions"
pending_transactions.short_description = "Mark selected transactions as pending"
cancel_transactions.short_description = "Cancel selected transactions"
reward_availability_set_available.short_description = "Set selected rewards as available"
reward_availability_set_on_demand.short_description = "Set selected rewards as on demand"
reward_availability_set_unavailable.short_description = "Set selected rewards as unavailable"
reward_set_active.short_description = "Set selected rewards as active"
reward_set_inactive.short_description = "Set selected rewards as inactive"




# REGISTERING AND SETTING UP MODELS FOR DJANGO ADMIN

@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active')
    search_fields = ('name', 'code')
    list_filter = ('is_active',)

@admin.register(RegionRep)
class RegionRepAdmin(admin.ModelAdmin):
    list_display = ('user', 'region', 'is_primary', 'date_from', 'date_to', 'is_active')
    list_filter = ('is_active', 'is_primary', 'region')
    search_fields = ('user__username', 'user__email', 'user__last_name', 'region__name')
    date_hierarchy = 'date_from'
    raw_id_fields = ('user',)
    
    def get_form(self, request, obj=None, **kwargs):
        """
        Customize the form to only show users in the Sales Reps group.
        """
        form = super().get_form(request, obj, **kwargs)
        if 'user' in form.base_fields:
            form.base_fields['user'].queryset = User.objects.filter(
                groups__name='Sales Reps'
            )
        return form

@admin.register(User)
class UserAdmin(ImportExportMixin, BaseUserAdmin):
    resource_class = OptimizedUserResource
    list_display = ('username', 'email', 'last_name', 'first_name', 'user_number', 'user_phone', 'region')
    search_fields = ('username', 'email', 'last_name', 'user_number')
    list_filter = ('is_staff', 'is_active', 'region')
    inlines = [UserContractInline]

    # Extend fieldsets to include custom fields from the User model
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Custom fields', {'fields': ('user_number', 'user_phone', 'region')}),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Custom fields', {'fields': ('user_number', 'user_phone', 'region')}),
    )

@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'last_activity', 'visit_count')
    list_filter = ('date', 'user')
    search_fields = ('user__username', 'user__email', 'user__last_name')
    date_hierarchy = 'date'

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'prefix')
    search_fields = ('name', 'prefix')

@admin.register(UserContract)
class UserContractAdmin(ImportExportMixin, admin.ModelAdmin):
    resource_class = UserContractResource
    list_display = ('user_id', 'contract_date_from', 'contract_date_to', 'is_active')
    search_fields = ('user_id__username', 'user_id__email', 'user_id__user_number')
    list_filter = ('is_active', 'contract_date_from', 'contract_date_to')
    inlines = [UserContractGoalInline]

@admin.register(UserContractGoal)
class UserContractGoalAdmin(ImportExportMixin, admin.ModelAdmin):
    resource_class = UserContractGoalResource
    list_display = ('user_contract', 'goal_period_from', 'goal_period_to', 'goal_value', 'goal_base', 'evaluation_frequency', 'allow_full_period_recovery', 'bonus_percentage')
    list_filter = ('goal_period_from', 'goal_period_to')
    search_fields = ('user_contract__user_id__email',)

@admin.register(GoalEvaluation)
class GoalEvaluationAdmin(admin.ModelAdmin):
    list_display = ('goal', 'evaluation_date', 'period_start', 'period_end', 'actual_turnover', 'target_turnover', 'baseline_turnover', 'is_achieved', 'bonus_points', 'evaluation_type')
    list_filter = ('evaluation_date', 'is_achieved', 'evaluation_type')
    search_fields = ('goal__user_contract__user_id__username', 'goal__user_contract__user_id__email')

@admin.register(PointsTransaction)
class PointsTransactionAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ('user', 'type', 'value', 'status', 'date', 'description')
    search_fields = ('user__username', 'user__email', 'user__user_number')
    list_filter = ('type', 'status', 'date')
    readonly_fields = ('created_at',)
    actions = [confirm_transactions, pending_transactions, cancel_transactions]

@admin.register(BrandBonus)
class BrandBonusAdmin(ExportMixin, admin.ModelAdmin):
    list_display = ('name', 'brand_id', 'points_ratio')
    search_fields = ('name', 'brand_id__name')

@admin.register(FileUpload)
class FileUploadAdmin(admin.ModelAdmin):
    list_display = ('status', 'uploaded_at', 'file', 'processed_at', 'uploaded_by')
    list_filter = ('status', 'uploaded_at', 'uploaded_by')
    readonly_fields = ('uploaded_at', 'processed_at', 'status', 'error_message')

@admin.register(Reward)
class RewardAdmin(ImportExportMixin, admin.ModelAdmin):
    resource_class = RewardResource
    list_display = ('abra_code', 'name', 'point_cost', 'brand', 'is_active', 'availability', 'in_showcase')
    list_filter = ('brand', 'is_active')
    search_fields = ('abra_code', 'name')
    readonly_fields = ('created_at',)
    actions = [reward_availability_set_available, reward_availability_set_on_demand, reward_availability_set_unavailable,
               reward_set_active, reward_set_inactive]

    actions.extend(['add_to_showcase', 'remove_from_showcase'])
    
    def add_to_showcase(self, request, queryset):
        updated = queryset.update(in_showcase=True)
        self.message_user(request, f"{updated} rewards added to public showcase.")
    add_to_showcase.short_description = "Add selected rewards to public showcase"
    
    def remove_from_showcase(self, request, queryset):
        updated = queryset.update(in_showcase=False)
        self.message_user(request, f"{updated} rewards removed from public showcase.")
    remove_from_showcase.short_description = "Remove selected rewards from public showcase"

@admin.register(RewardRequest)
class RewardRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'requested_at', 'status', 'total_points')
    list_filter = ('status',)
    search_fields = ('user__username', 'user__email')
    actions = [approve_requests, reject_requests]
    inlines = [RewardRequestItemInline]

@admin.register(RewardRequestItem)
class RewardRequestItemAdmin(admin.ModelAdmin):
    list_display = ('reward_request', 'reward', 'quantity', 'point_cost')

@admin.register(EmailNotification)
class EmailNotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'subject', 'status', 'created_at', 'sent_at')
    list_filter = ('status', 'created_at', 'sent_at')
    search_fields = ('user__username', 'user__email', 'subject')
    readonly_fields = ('created_at', 'sent_at')

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'client_number', 'invoice_date', 'invoice_type', 'total_amount')
    list_filter = ('invoice_type', 'invoice_date')
    search_fields = ('invoice_number', 'client_number')
    date_hierarchy = 'invoice_date'
    inlines = [InvoiceBrandTurnoverInline]

@admin.register(InvoiceBrandTurnover)
class InvoiceBrandTurnoverAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'brand', 'amount')
    list_filter = ('brand',)
    search_fields = ('invoice__invoice_number', 'invoice__client_number', 'brand__name')

# TEST ADDITION, A BIT MESSY
import csv
import datetime
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.db.models import Sum, Value, DecimalField
from django.db.models.functions import Coalesce

def export_turnover_action(modeladmin, request, queryset):
    """
    Admin action to export selected users' turnover data.
    This will appear in the Actions dropdown in Django Admin.
    """
    date_from = datetime.date(2025, 1, 1)
    date_to = datetime.date.today()
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="users_turnover_{datetime.date.today().isoformat()}.csv"'
    
    writer = csv.writer(response)
    # CSV headers
    writer.writerow(['User Number', 'Username', 'Email', 'Total Net Turnover', 'Contract Brands'])
    
    for user in queryset:
        # Skip users without user_number
        if not hasattr(user, 'user_number') or not user.user_number:
            writer.writerow([f'No user_number', user.username, user.email, '0.00', 'No contract'])
            continue
            
        try:
            # Get user's active contract
            active_contract = UserContract.objects.get(
                user_id=user, 
                is_active=True
            )
            contract_brands = [bb.brand_id for bb in active_contract.brandbonuses.all()]
            brand_names = [brand.name for brand in contract_brands]  # Assuming Brand has a 'name' field
        except UserContract.DoesNotExist:
            writer.writerow([user.user_number, user.username, user.email, '0.00', 'No active contract'])
            continue
        
        if not contract_brands:
            writer.writerow([user.user_number, user.username, user.email, '0.00', 'No contracted brands'])
            continue
        
        total_net_turnover = 0
        
        # Calculate turnover for each contracted brand
        for brand in contract_brands:
            # Invoice turnover
            invoice_turnover = InvoiceBrandTurnover.objects.filter(
                invoice__client_number=user.user_number,
                invoice__invoice_date__gte=date_from,
                invoice__invoice_date__lte=date_to,
                invoice__invoice_type='INVOICE',
                brand=brand
            ).aggregate(
                total=Coalesce(Sum('amount'), Value(0, output_field=DecimalField()))
            )['total']
            
            # Credit note turnover
            credit_turnover = InvoiceBrandTurnover.objects.filter(
                invoice__client_number=user.user_number,
                invoice__invoice_date__gte=date_from,
                invoice__invoice_date__lte=date_to,
                invoice__invoice_type='CREDIT_NOTE',
                brand=brand
            ).aggregate(
                total=Coalesce(Sum('amount'), Value(0, output_field=DecimalField()))
            )['total']
            
            # Add to total
            total_net_turnover += (invoice_turnover - credit_turnover)
        
        # Write row to CSV
        writer.writerow([
            user.user_number, 
            user.username, 
            user.email,
            f'{total_net_turnover:.2f}',
            ', '.join(brand_names)
        ])
    
    return response

# Set the action description (what appears in the dropdown)
export_turnover_action.short_description = "Export turnover data for selected users"


# Custom UserAdmin class
class CustomUserAdmin(BaseUserAdmin):
    # Add your custom action to the actions list
    actions = BaseUserAdmin.actions + (export_turnover_action, )
    
    # Optional: Add more fields to the list display
    list_display = BaseUserAdmin.list_display + ('date_joined',)
    
    # Optional: Add filters
    list_filter = BaseUserAdmin.list_filter + ('date_joined',)


admin.site.add_action(export_turnover_action, 'export_turnover_data')