from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django_q.tasks import async_task
from pa_bonus.models import EmailNotification, User, PointsTransaction, RewardRequest
import logging

# Configure logging
logger = logging.getLogger(__name__)

def send_email_notification(user, subject, message):
    """
    Send an email to a user and log it in the notifications table. If DEBUG=True, always sends it to the admin email.
    """
    notification = EmailNotification.objects.create(
        user=user,
        subject=subject,
        message=message
    )
    logger.info(f"Created notification for user {user.username}")
    
    try:
        # Get User email or, if in DEBUG, admin email
        if settings.DEBUG:
            email_to = User.objects.filter(username='admin').first().email
        else:
            email_to = user.email
        
        logger.info(f"Scheduling a task to send an email to {email_to}")

        async_task(
            'pa_bonus.tasks.send_email_task', 
            notification_id=notification.id,
            recipient_email=email_to,
            subject=subject,
            message=message
        )

        return True
    except Exception as e:
        notification.status = 'FAILED'
        notification.save()
        logger.error(f"Failed to send email to {email_to}: {str(e)}")
        return False

def notify_points_added(transaction):
    """
    Notify user when points are added to their account
    """
    if transaction.value <= 0:
        return
    
    subject = "Points added to your Bonus Program account"
    message = f"""Hello {transaction.user.first_name},

{transaction.value} points have been added to your Bonus Program account.
Transaction details:
- Date: {transaction.date}
- Description: {transaction.description}
- Brand: {transaction.brand.name if transaction.brand else 'Not specified'}

Your current balance is {transaction.user.get_balance()} points.

Thank you for your business!
Bonus Program Team
"""
    
    return send_email_notification(transaction.user, subject, message)

def notify_reward_status_change(reward_request):
    """
    Notify user when reward request status changes
    """
    subject = f"Your reward request status has been updated"
    message = f"""Hello {reward_request.user.first_name},

Your reward request (ID: {reward_request.id}) status has been updated to: {reward_request.get_status_display()}.

Request details:
- Points used: {reward_request.total_points}
- Requested on: {reward_request.requested_at.strftime('%Y-%m-%d')}
- Current status: {reward_request.get_status_display()}

Your current point balance is {reward_request.user.get_balance()} points.

Thank you for participating in our Bonus Program!
Bonus Program Team
"""
    
    return send_email_notification(reward_request.user, subject, message)