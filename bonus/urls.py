"""
URL configuration for bonus project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path
from django.shortcuts import redirect
from django.views.generic import TemplateView, RedirectView
from pa_bonus.views import views_managers as vm, views_users as vu, views_public as vp, views_reports as vr
from pa_bonus.forms import EmailAuthenticationForm

def home_redirect(request):
    """Redirects the root URL to dashboard."""
    return redirect('dashboard')

urlpatterns = []

# PUBLIC FACING URLS
urlpatterns.extend([
    path('', home_redirect, name='home_redirect'),
    path('login/', LoginView.as_view(template_name='login.html', authentication_form=EmailAuthenticationForm), name='login'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
    path('contact/', TemplateView.as_view(template_name='contact.html'), name='contact'),
    path('privacy-policy/', TemplateView.as_view(template_name='privacy_policy.html'), name='privacy_policy'),
    path('katalog/', vp.PublicCatalogueView.as_view(), name='public_catalogue'),
    path('registrace', RedirectView.as_view(url="https://docs.google.com/forms/d/e/1FAIpQLSc6MCWiLwryMeB5FwUgraf_2XvmvuYedqcx1nDHjLOzlJEQeQ/viewform?usp=sf_link"), name='registration')
])

# CLIENT FACING URLS
urlpatterns.extend([
    path('dashboard/', vu.DashboardView.as_view(), name='dashboard'),
    path('history/', vu.HistoryView.as_view(), name='history'),
    path('history/detail/<int:pk>/', vu.HistoryDetailView.as_view(), name='history_detail'),
    path('rewards/', vu.RewardsView.as_view(), name='rewards'),
    path('rewards/requests/', vu.RewardsRequestsView.as_view(), name='reward_requests'),
    path('rewards/requests/detail/<int:pk>', vu.RewardsRequestConfirmationView.as_view(), name='rewards_request_detail'), 
])

# MANAGER FACING URLS
urlpatterns.extend([
    path('manager/', vm.ManagerDashboardView.as_view(), name='manager_dashboard'),
    path('manager/upload/', vm.upload_file, name='upload_file'),
    path('manager/upload_history/', vm.upload_history, name='upload_history'),
    path('manager/reward-requests/', vm.ManagerRewardRequestListView.as_view(), name="manager_reward_requests"),
    path('manager/reward-requests/<int:pk>/', vm.ManagerRewardRequestDetailView.as_view(), name='manager_reward_request_detail'),
    path('manager/reward-requests/<int:pk>/export/', vm.ExportTelemarketingFileView.as_view(), name='export_telemarketing_file'),
    path('manager/transactions/approve/', vm.TransactionApprovalView.as_view(), name='transaction_approval'),
    path('manager/sms-export/', vm.SMSExportView.as_view(), name='sms_export'),
    path('manager/clients/create/', vm.ClientCreateView.as_view(), name='manager_client_create'),
    path('manager/clients/', vm.ClientListView.as_view(), name='manager_clients'),
    path('manager/clients/<int:pk>/', vm.ClientDetailView.as_view(), name='manager_client_detail'),
    path('manager/upload_stock/', vm.upload_stock, name='upload_stock'),
    path('manager/user-activity/', vm.UserActivityDashboardView.as_view(), name='user_activity_dashboard'),
    # Enhanced Reward Request Management
    path('manager/reward-requests-enhanced/', 
         vm.EnhancedRewardRequestListView.as_view(), 
         name='enhanced_reward_requests'),
    path('manager/reward-requests/quick-edit/<int:pk>/', 
         vm.RewardRequestQuickEditView.as_view(), 
         name='reward_request_quick_edit'),
    path('manager/reports/', vr.ReportsHubView.as_view(), name='reports_hub'),
    path('manager/reports/download/', vr.ReportDownloadView.as_view(), name='report_download'),
])

# ADMIN URLS
urlpatterns.extend([
    path('admin/', admin.site.urls),
])

from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)