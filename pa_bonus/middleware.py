from django.utils import timezone
from pa_bonus.models import UserActivity
import logging

logger = logging.getLogger(__name__)

class UserActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Code executed before the view
        if request.user.is_authenticated:
            # Get or create activity record for today
            try:
                UserActivity.objects.update_or_create(
                    user=request.user,
                    date=timezone.now().date(),
                    defaults={
                        'last_activity': timezone.now(),
                        'visit_count': UserActivity.objects.filter(
                            user=request.user,
                            date=timezone.now().date()
                        ).values_list('visit_count', flat=True).first() or 0 + 1
                    }
                )
            except Exception as e:
                # Don't break the site if tracking fails
                logger.error(f"Error tracking user activity: {str(e)}")
                
        response = self.get_response(request)
        return response