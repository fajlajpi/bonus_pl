from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import TemplateView, ListView, DetailView, View
from django.db.models import Q
from django.db import transaction
from django.utils import timezone
from pa_bonus.models import (PointsTransaction, UserContract, Reward, RewardRequest, RewardRequestItem,
                             UserContractGoal, InvoiceBrandTurnover)
from pa_bonus.utilities import calculate_turnover_for_goal
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
            
            # NEW: Get active extra goals
            active_goals = UserContractGoal.objects.filter(
                user_contract=contract,
                goal_period_from__lte=today,
                goal_period_to__gte=today
            )
            
            if active_goals.exists():
                # Get current period for the first active goal
                goal = active_goals.first()
                periods = goal.get_evaluation_periods()
                
                current_period = None
                for start, end, is_final in periods:
                    if start <= today <= end:
                        current_period = (start, end, is_final)
                        break
                
                if current_period:
                    # Calculate progress for current period
                    targets = goal.get_period_targets(current_period[0], current_period[1])
                    actual_turnover = calculate_turnover_for_goal(
                        user, goal.brands.all(), current_period[0], current_period[1]
                    )
                    progress = (actual_turnover / targets['goal_value'] * 100) if targets['goal_value'] > 0 else 0
                    
                    context['active_goal'] = {
                        'goal': goal,
                        'period_start': current_period[0],
                        'period_end': current_period[1],
                        'target': targets['goal_value'],
                        'actual': actual_turnover,
                        'progress': min(progress, 100),
                        'remaining': max(0, targets['goal_value'] - actual_turnover)
                    }
        except UserContract.DoesNotExist:
            context['contract'] = None
            context['brand_bonuses'] = []
            context['active_goal'] = None
        
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

class ExtraGoalsView(LoginRequiredMixin, TemplateView):
    """
    Displays the extra goals page (currently under construction).
    """
    template_name = 'extra_goals.html'

class ExtraGoalsDetailView(LoginRequiredMixin, View):
    """
    Displays detailed extra goals progress for the logged-in user.
    Shows current goals, evaluation periods, and progress tracking.
    """
    template_name = 'extra_goals_detail.html'
    login_url = 'login'
    
    def _calculate_potential_points(self, goal, targets, already_awarded=0):
        """
        Calculate potential points for a milestone if the goal is achieved.
        
        Args:
            goal: UserContractGoal instance
            targets: Dict with 'goal_value' and 'goal_base' for the period
            already_awarded: Points already awarded for this goal (for cap calculation)
            
        Returns:
            int: Potential points that would be awarded
        """
        # Calculate raw points: percentage of the increase from base to goal
        raw_points = int((targets['goal_value'] - targets['goal_base']) * goal.bonus_percentage)
        
        # Apply simple cap logic - for user display, we can use a simplified version
        # The actual cap is proportional to contract length, but for display we'll show the raw calculation
        return max(0, raw_points)
    
    def _get_total_awarded_points(self, goal):
        """
        Get total points already awarded for this goal across all evaluations.
        
        Args:
            goal: UserContractGoal instance
            
        Returns:
            int: Total points already awarded
        """
        from django.db.models import Sum
        return goal.evaluations.aggregate(
            total=Sum('bonus_points')
        )['total'] or 0
    
    def get(self, request):
        user = request.user
        today = timezone.now().date()
        
        # Get active contract
        try:
            active_contract = UserContract.objects.get(
                user_id=user,
                is_active=True
            )
        except UserContract.DoesNotExist:
            return render(request, self.template_name, {
                'error': 'No active contract found',
                'goals': []
            })
        
        # Get all extra goals for the active contract
        goals = UserContractGoal.objects.filter(
            user_contract=active_contract
        ).prefetch_related('brands', 'evaluations')
        
        goals_data = []
        
        for goal in goals:
            # Get evaluation periods
            periods = goal.get_evaluation_periods()
            period_data = []
            
            # Get total points already awarded for cap calculations
            already_awarded = self._get_total_awarded_points(goal)
            
            for start_date, end_date, is_final in periods:
                # Get targets for this period
                targets = goal.get_period_targets(start_date, end_date)
                
                # Calculate actual turnover for this period
                actual_turnover = calculate_turnover_for_goal(
                    user, goal.brands.all(), start_date, end_date
                )
                
                # Check if this period has been evaluated
                evaluation = goal.evaluations.filter(
                    period_start=start_date,
                    period_end=end_date
                ).first()
                
                # Determine period status
                if evaluation:
                    status = 'achieved' if evaluation.is_achieved else 'failed'
                    bonus_points = evaluation.bonus_points
                    potential_points = 0  # No potential points for completed evaluations
                elif end_date < today:
                    status = 'pending_evaluation'
                    bonus_points = 0
                    potential_points = 0  # Will be calculated when evaluated
                elif start_date <= today <= end_date:
                    status = 'in_progress'
                    bonus_points = 0
                    # Calculate potential points for in-progress periods
                    potential_points = self._calculate_potential_points(goal, targets, already_awarded)
                else:
                    status = 'future'
                    bonus_points = 0
                    potential_points = 0  # Don't show potential for future periods
                
                # Calculate progress percentage
                progress = (actual_turnover / targets['goal_value'] * 100) if targets['goal_value'] > 0 else 0
                
                period_data.append({
                    'start': start_date,
                    'end': end_date if is_final else end_date - datetime.timedelta(days=1),
                    'is_final': is_final,
                    'target': targets['goal_value'],
                    'baseline': targets['goal_base'],
                    'actual': actual_turnover,
                    'progress': progress,
                    'status': status,
                    'evaluation': evaluation,
                    'bonus_points': bonus_points,
                    'potential_points': potential_points,  # New field for potential points
                    'is_current': start_date <= today <= end_date
                })
            
            # Calculate overall progress
            total_actual = sum(p['actual'] for p in period_data)
            total_progress = (total_actual / goal.goal_value * 100) if goal.goal_value > 0 else 0
            
            goals_data.append({
                'goal': goal,
                'periods': period_data,
                'total_progress': min(total_progress, 100),
                'total_actual': total_actual,
                'brands': goal.brands.all()
            })
        
        context = {
            'contract': active_contract,
            'goals': goals_data,
            'today': today
        }
        
        return render(request, self.template_name, context)