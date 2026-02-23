"""
Sales Rep views for the bonus platform.

Sales Reps are a middle layer between clients and managers. They can:
- View a dashboard with their region's summary stats
- Browse all clients in their assigned region(s)
- View detailed client information (invoices, points, rewards) — read-only
- View reward requests from clients in their region(s)
- Create reward requests on behalf of their clients
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import View, ListView
from django.db.models import Sum, Count, Q, Value, DecimalField
from django.db.models.functions import Coalesce
from django.db import transaction
from django.utils import timezone

from pa_bonus.models import (
    User, Region, RegionRep, UserContract, PointsTransaction,
    InvoiceBrandTurnover, Brand, BrandBonus,
    Reward, RewardRequest, RewardRequestItem,
)
from pa_bonus.utilities import SalesRepRequiredMixin

from datetime import date, timedelta, datetime


def get_rep_regions(user):
    """
    Return the active Region queryset for a Sales Rep user.

    Args:
        user: The authenticated User instance (must be in 'Sales Reps' group).

    Returns:
        QuerySet[Region]: Regions the rep is currently assigned to.
    """
    region_ids = RegionRep.objects.filter(
        user=user,
        is_active=True,
    ).values_list('region_id', flat=True)
    return Region.objects.filter(id__in=region_ids, is_active=True)


def get_rep_clients(user):
    """
    Return the base client queryset for a Sales Rep — all active, non-staff
    users whose region is one of the rep's assigned regions.
    """
    regions = get_rep_regions(user)
    return User.objects.filter(
        is_active=True,
        is_staff=False,
        region__in=regions,
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
class SalesRepDashboardView(SalesRepRequiredMixin, View):
    """
    Overview dashboard for a Sales Rep showing their region(s) summary.
    """
    template_name = 'salesrep/dashboard.html'

    def get(self, request):
        regions = get_rep_regions(request.user)
        clients = get_rep_clients(request.user)

        # Summary statistics
        total_clients = clients.count()

        clients_with_contracts = clients.filter(
            usercontract__is_active=True,
        ).distinct().count()

        # Aggregate confirmed points across all rep's clients
        total_confirmed_points = PointsTransaction.objects.filter(
            user__in=clients,
            status='CONFIRMED',
        ).aggregate(
            total=Coalesce(Sum('value'), Value(0)),
        )['total']

        # Pending reward requests in the rep's regions
        pending_requests = RewardRequest.objects.filter(
            user__in=clients,
            status__in=['DRAFT', 'PENDING'],
        ).count()

        # Top 10 clients by available points
        top_clients = clients.annotate(
            available_points=Coalesce(
                Sum('pointstransaction__value',
                    filter=Q(pointstransaction__status='CONFIRMED')),
                Value(0),
            ),
        ).filter(available_points__gt=0).order_by('-available_points')[:10]

        context = {
            'regions': regions,
            'total_clients': total_clients,
            'clients_with_contracts': clients_with_contracts,
            'total_confirmed_points': total_confirmed_points,
            'pending_requests': pending_requests,
            'top_clients': top_clients,
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------
# Client List
# ---------------------------------------------------------------------------
class SalesRepClientListView(SalesRepRequiredMixin, View):
    """
    Lists all clients in the rep's region(s) with point balances and turnover.
    """
    template_name = 'salesrep/client_list.html'

    def get(self, request):
        clients = get_rep_clients(request.user)
        regions = get_rep_regions(request.user)

        # Optional region filter (if rep has multiple regions)
        region_id = request.GET.get('region', '')
        if region_id and region_id != 'all':
            clients = clients.filter(region_id=region_id)

        # Date range filters (default: current year)
        current_year = datetime.now().year
        year_from = int(request.GET.get('year_from', current_year))
        month_from = int(request.GET.get('month_from', 1))
        year_to = int(request.GET.get('year_to', current_year))
        month_to = int(request.GET.get('month_to', 12))

        date_from = date(year_from, month_from, 1)
        if month_to == 12:
            date_to = date(year_to + 1, 1, 1) - timedelta(days=1)
        else:
            date_to = date(year_to, month_to + 1, 1) - timedelta(days=1)

        # Annotate with points
        clients = clients.annotate(
            confirmed_points=Coalesce(
                Sum('pointstransaction__value',
                    filter=Q(
                        pointstransaction__status='CONFIRMED',
                        pointstransaction__date__gte=date_from,
                        pointstransaction__date__lte=date_to,
                    )),
                Value(0),
            ),
            available_points=Coalesce(
                Sum('pointstransaction__value',
                    filter=Q(pointstransaction__status='CONFIRMED')),
                Value(0),
            ),
        ).order_by('last_name', 'first_name')

        # Build per-client data (turnover from contract brands)
        client_data = []
        for client in clients:
            try:
                active_contract = UserContract.objects.get(user_id=client, is_active=True)
                contract_brands = [bb.brand_id for bb in active_contract.brandbonuses.all()]
                turnover = InvoiceBrandTurnover.objects.filter(
                    invoice__client_number=client.user_number,
                    invoice__invoice_date__gte=date_from,
                    invoice__invoice_date__lte=date_to,
                    invoice__invoice_type='INVOICE',
                    brand__in=contract_brands,
                ).aggregate(
                    total=Coalesce(Sum('amount'), Value(0, output_field=DecimalField())),
                )['total']
            except UserContract.DoesNotExist:
                active_contract = None
                turnover = 0

            client_data.append({
                'user': client,
                'contract': active_contract,
                'turnover': turnover,
            })

        context = {
            'clients': client_data,
            'regions': regions,
            'selected_region': region_id,
            'year_from': year_from,
            'month_from': month_from,
            'year_to': year_to,
            'month_to': month_to,
            'date_from': date_from,
            'date_to': date_to,
            'months': [(i, date(2000, i, 1).strftime('%B')) for i in range(1, 13)],
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------
# Client Detail (read-only)
# ---------------------------------------------------------------------------
class SalesRepClientDetailView(SalesRepRequiredMixin, View):
    """
    Detailed read-only view of a single client, showing brand turnovers,
    point history, and reward requests.
    """
    template_name = 'salesrep/client_detail.html'

    def get(self, request, pk):
        # Ensure the client belongs to one of the rep's regions
        allowed_clients = get_rep_clients(request.user)
        client = get_object_or_404(allowed_clients, pk=pk)

        # Date range
        current_year = datetime.now().year
        year_from = int(request.GET.get('year_from', current_year))
        month_from = int(request.GET.get('month_from', 1))
        year_to = int(request.GET.get('year_to', current_year))
        month_to = int(request.GET.get('month_to', 12))

        date_from = date(year_from, month_from, 1)
        if month_to == 12:
            date_to = date(year_to + 1, 1, 1) - timedelta(days=1)
        else:
            date_to = date(year_to, month_to + 1, 1) - timedelta(days=1)

        # Contract & brands
        try:
            active_contract = UserContract.objects.get(user_id=client, is_active=True)
            contract_brands = [bb.brand_id for bb in active_contract.brandbonuses.all()]
        except UserContract.DoesNotExist:
            active_contract = None
            contract_brands = []

        # Brand turnovers for the period
        all_brands = Brand.objects.all()
        brand_turnovers = []
        for brand in all_brands:
            inv = InvoiceBrandTurnover.objects.filter(
                invoice__client_number=client.user_number,
                invoice__invoice_date__gte=date_from,
                invoice__invoice_date__lte=date_to,
                invoice__invoice_type='INVOICE',
                brand=brand,
            ).aggregate(total=Coalesce(Sum('amount'), Value(0, output_field=DecimalField())))['total']

            cn = InvoiceBrandTurnover.objects.filter(
                invoice__client_number=client.user_number,
                invoice__invoice_date__gte=date_from,
                invoice__invoice_date__lte=date_to,
                invoice__invoice_type='CREDIT_NOTE',
                brand=brand,
            ).aggregate(total=Coalesce(Sum('amount'), Value(0, output_field=DecimalField())))['total']

            pts = PointsTransaction.objects.filter(
                user=client, date__gte=date_from, date__lte=date_to,
                brand=brand, status='CONFIRMED',
            ).aggregate(total=Coalesce(Sum('value'), Value(0)))['total']

            if inv > 0 or cn > 0 or pts != 0:
                brand_turnovers.append({
                    'brand': brand,
                    'invoice_turnover': inv,
                    'credit_turnover': cn,
                    'net_turnover': inv - cn,
                    'points': pts,
                    'in_contract': brand in contract_brands,
                })

        brand_turnovers.sort(key=lambda x: x['net_turnover'], reverse=True)

        # Point totals
        point_totals = {
            'available': client.get_balance(),
            'period_confirmed': PointsTransaction.objects.filter(
                user=client, date__gte=date_from, date__lte=date_to, status='CONFIRMED',
            ).aggregate(total=Coalesce(Sum('value'), Value(0)))['total'],
        }

        # Recent transactions
        recent_transactions = PointsTransaction.objects.filter(
            user=client,
        ).order_by('-date', '-created_at')[:20]

        # Reward requests
        reward_requests = RewardRequest.objects.filter(
            user=client,
        ).order_by('-requested_at')[:10]

        context = {
            'client': client,
            'active_contract': active_contract,
            'brand_turnovers': brand_turnovers,
            'point_totals': point_totals,
            'recent_transactions': recent_transactions,
            'reward_requests': reward_requests,
            'date_from': date_from,
            'date_to': date_to,
            'year_from': year_from,
            'month_from': month_from,
            'year_to': year_to,
            'month_to': month_to,
            'months': [(i, date(2000, i, 1).strftime('%B')) for i in range(1, 13)],
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------
# Reward Requests (read-only list)
# ---------------------------------------------------------------------------
class SalesRepRewardRequestsView(SalesRepRequiredMixin, ListView):
    """
    Lists reward requests from clients in the rep's region(s).
    """
    template_name = 'salesrep/reward_requests.html'
    context_object_name = 'reward_requests'

    def get_queryset(self):
        clients = get_rep_clients(self.request.user)
        queryset = RewardRequest.objects.filter(
            user__in=clients,
        ).select_related('user').order_by('-requested_at')

        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['selected_status'] = self.request.GET.get('status', '')
        return context


# ---------------------------------------------------------------------------
# Create Reward Request on behalf of a client
# ---------------------------------------------------------------------------
class SalesRepCreateRewardRequestView(SalesRepRequiredMixin, View):
    """
    Allows a Sales Rep to create and submit a reward request for a client.
    The flow mirrors the client's own RewardsView but operates on the client's
    account.
    """
    template_name = 'salesrep/create_reward_request.html'

    def _get_client(self, request, pk):
        """Validate that the client belongs to the rep's region."""
        allowed = get_rep_clients(request.user)
        return get_object_or_404(allowed, pk=pk)

    def get(self, request, pk):
        client = self._get_client(request, pk)

        # Get client's brands
        user_contracts = UserContract.objects.filter(user_id=client, is_active=True)
        user_brands = set()
        for contract in user_contracts:
            for bonus in contract.brandbonuses.all():
                user_brands.add(bonus.brand_id)

        available_rewards = Reward.objects.filter(
            is_active=True,
        ).filter(
            Q(brand__in=user_brands) | Q(brand__isnull=True),
        ).distinct().order_by('-point_cost')

        client_balance = client.get_balance()

        context = {
            'client': client,
            'rewards': available_rewards,
            'client_balance': client_balance,
        }
        return render(request, self.template_name, context)

    @transaction.atomic
    def post(self, request, pk):
        client = self._get_client(request, pk)

        reward_quantities = {}
        total_points = 0

        for key, value in request.POST.items():
            if key.startswith('reward_quantity_') and value.isdigit():
                reward_id = key.split('reward_quantity_')[1]
                quantity = int(value)
                if quantity <= 0:
                    continue
                try:
                    reward = Reward.objects.get(pk=reward_id)
                except Reward.DoesNotExist:
                    continue
                total_points += reward.point_cost * quantity
                reward_quantities[reward_id] = (reward, quantity)

        if not reward_quantities:
            messages.warning(request, "No items selected.")
            return redirect('salesrep_create_reward_request', pk=pk)

        client_balance = client.get_balance()
        if total_points > client_balance:
            messages.error(
                request,
                f"Client does not have enough points ({client_balance}) "
                f"for this request ({total_points} required).",
            )
            return redirect('salesrep_create_reward_request', pk=pk)

        # Create the request on behalf of the client
        note = request.POST.get('rep_note', '').strip()
        reward_request = RewardRequest.objects.create(
            user=client,
            description=f"Created by Sales Rep {request.user.get_full_name()}",
        )

        for reward, quantity in reward_quantities.values():
            RewardRequestItem.objects.create(
                reward_request=reward_request,
                reward=reward,
                quantity=quantity,
                point_cost=reward.point_cost,
            )

        reward_request.save()  # recalculates total_points

        # Save optional note
        if note:
            reward_request.note = note
            reward_request.save()

        # Auto-submit (set to PENDING and create the claim transaction)
        reward_request.status = 'PENDING'
        reward_request.save()

        PointsTransaction.objects.create(
            value=-reward_request.total_points,
            date=reward_request.requested_at,
            user=client,
            description="Reward claim (via Sales Rep)",
            type="REWARD_CLAIM",
            status="CONFIRMED",
            reward_request=reward_request,
        )

        messages.success(
            request,
            f"Reward request created for {client.first_name} {client.last_name} "
            f"({reward_request.total_points} points).",
        )
        return redirect('salesrep_client_detail', pk=pk)
