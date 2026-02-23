from django.views.generic import TemplateView
from pa_bonus.models import Reward
from django.shortcuts import redirect


class PublicCatalogueView(TemplateView):
    """
    Public view for showcasing selected rewards from the catalogue.
    
    This view presents rewards marked for showcase in a grid-based layout
    without showing point costs or availability status.
    
    If a user is already logged in, they will be redirected to the full 
    rewards view where they can see all details and add items to cart.
    
    Attributes:
        template_name (str): Name of the template to render the view.
    """
    template_name = 'catalogue_public.html'
    
    def dispatch(self, request, *args, **kwargs):
        """
        Override dispatch to check if the user is authenticated.
        If they are, redirect them to the complete rewards view.
        """
        if request.user.is_authenticated:
            return redirect('rewards')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Filter rewards that should be in the showcase and are active
        showcase_rewards = Reward.objects.filter(
            in_showcase=True, 
            is_active=True
        ).select_related('brand')
        
        context['rewards'] = showcase_rewards
        return context