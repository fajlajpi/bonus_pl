from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import TemplateView, ListView, DetailView, View
from django.db.models import Q
from django.db import transaction
from django.utils import timezone
from pa_bonus.models import (PointsTransaction, UserContract, Reward, RewardRequest, RewardRequestItem,)
import datetime

class DashboardView(LoginRequiredMixin, TemplateView):
    """
    Main dashboard view with current point balance and links for logged-in users.

    This dashboard provides an overview of the users point balance, active contract
    and its parameters, and links to other parts of the system. It's a central hub.

    Attributes:
        template_name (str): Template to render the dashboard.
        login_url (str): Redirect url for non-authenticated users.
    """
    template_name = 'dashboard.html'
    login_url = 'login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = timezone.now().date()
        
        # Existing code...
        # Get the user's active contract and bonuses
        try:
            contract = UserContract.objects.get(
                user_id = user,
                is_active = True
            )
            context['contract'] = contract
            context['brand_bonuses'] = contract.brandbonuses.all()
            
        except UserContract.DoesNotExist:
            context['contract'] = None
            context['brand_bonuses'] = []
        
        # Calculate current point total
        total_points = user.get_balance()
        context['total_points'] = total_points
        
        return context

class HistoryView(LoginRequiredMixin, ListView):
    """
    Displays a history of the user's point transactions.

    This view lists all the user's transactions in descending chronological order.

    Attributes:
        template_name (str): Template to render the transaction history page.
        context_object_name (str): Name of the context object for the template.
        login_url (str): Redirect url for non-authenticated users.
    """
    template_name = 'history.html'
    context_object_name = 'transactions'
    login_url = 'login'

    def get_queryset(self):
        return PointsTransaction.objects.filter(
            user = self.request.user
        ).select_related('brand').order_by('-date', '-created_at')

class HistoryDetailView(LoginRequiredMixin, DetailView):
    """
    Displays the details of one point transaction.

    Attributes:
        template_name (str): Template to render the transaction detail page.
        context_object_name (str): Name of the context object for the template.
        login_url (str): Redirect url for non-authenticated users.
    """
    template_name = 'history_detail.html'
    context_object_name = 'transaction'
    login_url = 'login'

    def get_queryset(self):
        return PointsTransaction.objects.filter(
            user = self.request.user
        ).select_related('brand')

class RewardsView(LoginRequiredMixin, View):
    """
    Displays the available rewards as a simple list.

    This view will list the rewards available to the currently logged-in user. It also serves
    as a form to make a request for rewards.

    Attributes:
        template_name (str): Name of the template to render the view.
        login_url (str): Redirect url for non-authenticated users.
    """
    template_name = 'rewards.html'
    login_url = 'login'

    def get(self, request, *args, **kwargs):
        user = request.user

        # Get user's brands
        user_contracts = UserContract.objects.filter(user_id = user, is_active = True)
        user_brands = set()
        for contract in user_contracts:
            for bonus in contract.brandbonuses.all():
                user_brands.add(bonus.brand_id)

        # Get available rewards
        available_rewards = Reward.objects.filter(is_active=True).filter(Q(brand__in=user_brands) | Q(brand__isnull=True)).distinct().order_by('-point_cost')
        
        # Get user's point balance
        total_points = user.get_balance()

        context = {
            'rewards': available_rewards,
            'user_balance': total_points,
        }

        return render(request, self.template_name, context)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        user = request.user
        reward_quantities = {}
        total_points = 0

        # Collect and validate input before saving anything
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

        user_balance = user.get_balance()

        # Backend check — don't allow creation if not enough points
        if total_points > user_balance:
            messages.error(request, f"You do not have enough points ({user_balance}) to complete this request ({total_points} required).")
            return redirect('rewards')

        # Only now we create the request and items
        reward_request = RewardRequest.objects.create(user=user)

        for reward, quantity in reward_quantities.values():
            RewardRequestItem.objects.create(
                reward_request=reward_request,
                reward=reward,
                quantity=quantity,
                point_cost=reward.point_cost
            )

        reward_request.save()  # Updates total_points field
        messages.success(request, "Request saved successfully.")
        return redirect('rewards_request_detail', pk=reward_request.pk)

class RewardsRequestsView(LoginRequiredMixin, ListView):
    """
    Displays a list of user's requests for rewards.

    Attributes:
        template_name (str): Name of the template to render the view.
        login_url (str): Redirect url for non-authenticated users.
    """
    template_name = 'reward_requests.html'
    context_object_name = 'reward_requests'
    login_url = 'login'

    def get_queryset(self):
        return RewardRequest.objects.filter(
            user = self.request.user
        ).order_by('-requested_at')
    
class RequestsDetailView(LoginRequiredMixin, TemplateView):
    """
    Displays the detail of one specific request for rewards.

    Attributes:
        template_name (str): Name of the template to render the view.
        login_url (str): Redirect url for non-authenticated users.
    """
    template_name = 'request_detail.html'
    login_url = 'login'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        #PLACEHOLDER MESSAGE
        context['message'] = "Rewards system coming soon!"
        return context
    
class RewardsRequestConfirmationView(LoginRequiredMixin, View):
    """
    Asks the user to confirm their request for rewards.
    """
    template_name = 'rewards_request_detail.html'

    def get(self, request, pk):
        reward_request = get_object_or_404(RewardRequest, pk=pk)
        reward_request_items = RewardRequestItem.objects.filter(reward_request=reward_request)
        user_balance = request.user.get_balance()

        context = {
            'request': reward_request,
            'items': reward_request_items,
            'user_balance': user_balance,
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        reward_request = get_object_or_404(RewardRequest, pk=pk)
        if reward_request.status == 'DRAFT':
            # Save customer note with validation
            customer_note = request.POST.get('customer_note', '').strip()
            # Only save the note if it's longer than 5 characters, otherwise set to empty
            reward_request.note = customer_note if len(customer_note) > 5 else ''
            
            # Verify that user still has enough points
            user_balance = request.user.get_balance()
            if reward_request.total_points > user_balance:
                messages.error(request, f"Insufficient points: You have {user_balance} points but the request requires {reward_request.total_points} points.")
                return redirect('rewards_request_detail', pk=pk)
                
            # Update the status to Pending
            reward_request.status = "PENDING"
            reward_request.save()

            # Create a claim transaction so that the points are already blocked off
            points_transaction = PointsTransaction.objects.create(
                value = -reward_request.total_points,
                date=reward_request.requested_at,
                user=request.user,
                description="Reward claim",
                type="REWARD_CLAIM",
                status="CONFIRMED",
                reward_request=reward_request,
            )

            messages.success(request, f"Request {reward_request.id} confirmed successfully.")
            return redirect('reward_requests')
        else:
            messages.warning(request, f"Reward request was already submitted.")
            return redirect('reward_requests')
        