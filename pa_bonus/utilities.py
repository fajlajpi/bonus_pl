# UTILITY FUNCTIONS
from django.contrib.auth.mixins import UserPassesTestMixin

class ManagerGroupRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.groups.filter(name='Managers').exists()

class SalesRepRequiredMixin(UserPassesTestMixin):
    """Restricts access to users in the 'Sales Reps' group."""
    login_url = 'login'

    def test_func(self):
        return self.request.user.groups.filter(name='Sales Reps').exists()
    