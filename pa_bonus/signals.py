from django.db.models.signals import post_save
from django.dispatch import receiver
from pa_bonus.models import PointsTransaction, RewardRequest
from pa_bonus.notifications import notify_points_added, notify_reward_status_change

@receiver(post_save, sender=PointsTransaction)
def transaction_notification(sender, instance, created, **kwargs):
    """Send notification when a transaction is created or status changes to CONFIRMED"""
    if created and instance.status == 'CONFIRMED':
        notify_points_added(instance)

@receiver(post_save, sender=RewardRequest)
def reward_request_notification(sender, instance, **kwargs):
    """Send notification when reward request status changes, except for drafts"""
    if instance.status != 'DRAFT':
        notify_reward_status_change(instance)
