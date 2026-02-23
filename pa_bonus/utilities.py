# UTILITY FUNCTIONS
from django.contrib.auth.mixins import UserPassesTestMixin

class ManagerGroupRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.groups.filter(name='Managers').exists()
    