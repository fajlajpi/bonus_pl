from django.contrib.auth.backends import ModelBackend
from django.db.models import Q
from pa_bonus.models import User

class EmailOrUsernameModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        try:
            # Check if the username is an email (contains @)
            is_email = '@' in username
            
            # Build a case-insensitive query
            if is_email:
                # For emails, use iexact to make the lookup case-insensitive
                user = User.objects.get(email__iexact=username)
            else:
                # For usernames, use iexact to make the lookup case-insensitive
                user = User.objects.get(username__iexact=username)
            
            if user.check_password(password):
                return user
            return None
        except User.DoesNotExist:
            return None
        except User.MultipleObjectsReturned:
            # In the rare case where multiple users match the case-insensitive query
            # (this shouldn't happen with proper database constraints but just in case)
            # Get the first matching user
            if is_email:
                user = User.objects.filter(email__iexact=username).first()
            else:
                user = User.objects.filter(username__iexact=username).first()
                
            if user and user.check_password(password):
                return user
            return None
        
    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None