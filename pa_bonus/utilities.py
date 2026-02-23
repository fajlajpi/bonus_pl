# UTILITY FUNCTIONS
from django.contrib.auth.mixins import UserPassesTestMixin

class ManagerGroupRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.groups.filter(name='Managers').exists()
    

from django.db.models import Sum, Value, DecimalField
from django.db.models.functions import Coalesce
from pa_bonus.models import InvoiceBrandTurnover

def calculate_turnover_for_goal(user, brands, start_date, end_date):
    """
    Calculate turnover for a user and brands in date range.
    
    This is a utility function used by multiple views to calculate
    the total net turnover (invoices minus credit notes) for a specific
    user, set of brands, and date range.
    
    Args:
        user: User object
        brands: QuerySet or list of Brand objects
        start_date: Start date for calculation
        end_date: End date for calculation
        
    Returns:
        Decimal: Net turnover amount
    """
    # Get invoice turnover
    invoice_turnover = InvoiceBrandTurnover.objects.filter(
        invoice__client_number=user.user_number,
        invoice__invoice_date__gte=start_date,
        invoice__invoice_date__lt=end_date,
        invoice__invoice_type='INVOICE',
        brand__in=brands
    ).aggregate(
        total=Coalesce(Sum('amount'), Value(0, output_field=DecimalField()))
    )['total']
    
    # Get credit note turnover
    credit_turnover = InvoiceBrandTurnover.objects.filter(
        invoice__client_number=user.user_number,
        invoice__invoice_date__gte=start_date,
        invoice__invoice_date__lt=end_date,
        invoice__invoice_type='CREDIT_NOTE',
        brand__in=brands
    ).aggregate(
        total=Coalesce(Sum('amount'), Value(0, output_field=DecimalField()))
    )['total']
    
    return invoice_turnover - credit_turnover