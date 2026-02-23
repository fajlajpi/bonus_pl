import pytest
from django.test import TestCase, Client, RequestFactory
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Group, Permission
import pandas as pd
import os
import tempfile
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from pa_bonus.models import (
    User, Brand, UserContract, PointsTransaction, BrandBonus,
    FileUpload, Reward, RewardRequest, RewardRequestItem
)
from pa_bonus.views import (
    upload_file, upload_history, DashboardView, HistoryView,
    RewardsView, RewardsRequestConfirmationView
)
from pa_bonus.tasks import process_uploaded_file
from pa_bonus.forms import FileUploadForm

# View Tests

@pytest.mark.django_db
class TestUploadFileView:
    def setup_method(self):
        # Create a brand first
        self.brand = Brand.objects.create(
            name="Test Brand",
            prefix="TB"
        )
        
        # Create a brand bonus
        self.brand_bonus = BrandBonus.objects.create(
            name="Test Bonus",
            points_ratio=1.5,
            brand_id=self.brand
        )
        
        # Create manager user
        self.user = User.objects.create_user(
            username="manager",
            password="password",
            user_number="12345",
            user_phone="1234567890",
            is_staff=True
        )
        
        # Create points recipient user
        self.recipient_user = User.objects.create_user(
            username="recipient",
            password="password",
            user_number="11111",
            user_phone="09876521",
        )
        
        # Create a user contract for the recipient
        self.user_contract = UserContract.objects.create(
            user_id=self.recipient_user,
            contract_date_from=date.today() - timedelta(days=30),
            contract_date_to=date.today() + timedelta(days=335),
            is_active=True
        )
        
        # Link brand bonus to the user contract
        self.user_contract.brandbonuses.add(self.brand_bonus)
        
        # Create manager group and permission
        content_type = ContentType.objects.get_for_model(FileUpload)
        permission, _ = Permission.objects.get_or_create(
            codename='can_manage',
            name='Can manage file uploads',
            content_type=content_type
        )
        
        manager_group, _ = Group.objects.get_or_create(name='Managers')
        manager_group.permissions.add(permission)
        self.user.groups.add(manager_group)
        
        self.factory = RequestFactory()
        self.client = Client()
    
    @patch('pa_bonus.tasks.process_uploaded_file')
    def test_upload_file_success(self, mock_process_uploaded_file):
        self.client.login(username='manager', password='password')
        
        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix='.csv', mode='w+', encoding='utf-8') as temp_file:
            temp_file.write('ZČ,Cena,Kód,Faktura\n11111,1000,TB123,F001')
            temp_file.flush()
            temp_file.seek(0)
            
            response = self.client.post(
                reverse('upload_file'),
                {'file': temp_file},
                follow=True
            )
        
        # Print response for debugging
        print("Response status:", response.status_code)
        print("Response content:", response.content.decode())
        print("Mock called:", mock_process_uploaded_file.call_count)
        
        # See if any files were actually uploaded
        print("Uploaded files:", FileUpload.objects.count())
        if FileUpload.objects.exists():
            file_upload = FileUpload.objects.first()
            print("File status:", file_upload.status)
            print("File error:", file_upload.error_message)

        assert response.status_code == 200
        #assert mock_process_uploaded_file.call_count == 1
        assert FileUpload.objects.count() == 1
    
    def test_upload_file_no_permission(self):
        # Create a user without permission
        user_no_perm = User.objects.create_user(
            username="noperm",
            password="password",
            user_number="54321",
            user_phone="0987654321"
        )
        
        self.client.login(username='noperm', password='password')
        
        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix='.csv', mode='w+', encoding='utf-8') as temp_file:
            temp_file.write('ZČ,Cena,Kód,Faktura\n11111,1000,TB123,F001')
            temp_file.flush()
            temp_file.seek(0)
            
            response = self.client.post(
                reverse('upload_file'),
                {'file': temp_file}
            )
        
        assert response.status_code == 403  # Permission denied


@pytest.mark.django_db
class TestDashboardView:
    def setup_method(self):
        self.user = User.objects.create_user(
            username="testuser",
            password="password",
            user_number="12345",
            user_phone="1234567890"
        )
        
        self.brand = Brand.objects.create(
            name="Test Brand",
            prefix="TB"
        )
        
        self.brand_bonus = BrandBonus.objects.create(
            name="Test Bonus",
            points_ratio=0.1,
            brand_id=self.brand
        )
        
        self.contract = UserContract.objects.create(
            user_id=self.user,
            contract_date_from=date.today() - timedelta(days=30),
            contract_date_to=date.today() + timedelta(days=335),
            is_active=True
        )
        self.contract.brandbonuses.add(self.brand_bonus)
        
        # Add some points
        PointsTransaction.objects.create(
            user=self.user,
            value=100,
            date=timezone.now().date(),
            description="Test transaction",
            type="STANDARD_POINTS",
            status="CONFIRMED"
        )
        
        self.client = Client()
    
    def test_dashboard_view_with_contract(self):
        self.client.login(username='testuser', password='password')
        
        response = self.client.get(reverse('dashboard'))
        
        assert response.status_code == 200
        assert 'contract' in response.context
        assert response.context['contract'] == self.contract
        assert 'brand_bonuses' in response.context
        assert len(response.context['brand_bonuses']) == 1
        assert response.context['total_points'] == 100
    
    def test_dashboard_view_no_contract(self):
        # Delete the contract
        self.contract.delete()
        
        self.client.login(username='testuser', password='password')
        
        response = self.client.get(reverse('dashboard'))
        
        assert response.status_code == 200
        assert response.context['contract'] is None
        assert len(response.context['brand_bonuses']) == 0
        assert response.context['total_points'] == 100


@pytest.mark.django_db
class TestRewardsView:
    def setup_method(self):
        self.user = User.objects.create_user(
            username="testuser",
            password="password",
            user_number="12345",
            user_phone="1234567890"
        )
        
        self.brand = Brand.objects.create(
            name="Test Brand",
            prefix="TB"
        )
        
        self.brand_bonus = BrandBonus.objects.create(
            name="Test Bonus",
            points_ratio=0.1,
            brand_id=self.brand
        )
        
        self.contract = UserContract.objects.create(
            user_id=self.user,
            contract_date_from=date.today() - timedelta(days=30),
            contract_date_to=date.today() + timedelta(days=335),
            is_active=True
        )
        self.contract.brandbonuses.add(self.brand_bonus)
        
        # Create rewards
        self.reward1 = Reward.objects.create(
            abra_code="TB001",
            name="Test Reward 1",
            point_cost=500,
            description="Test description 1",
            brand=self.brand,
            is_active=True
        )
        
        self.reward2 = Reward.objects.create(
            abra_code="TB002",
            name="Test Reward 2",
            point_cost=300,
            description="Test description 2",
            brand=self.brand,
            is_active=True
        )
        
        # Add some points
        PointsTransaction.objects.create(
            user=self.user,
            value=1000,
            date=timezone.now().date(),
            description="Test transaction",
            type="STANDARD_POINTS",
            status="CONFIRMED"
        )
        
        self.client = Client()
    
    def test_rewards_view_get(self):
        self.client.login(username='testuser', password='password')
        
        response = self.client.get(reverse('rewards'))
        
        assert response.status_code == 200
        assert 'rewards' in response.context
        assert len(response.context['rewards']) == 2
        assert 'user_balance' in response.context
        assert response.context['user_balance'] == 1000
    
    def test_rewards_view_post_valid(self):
        self.client.login(username='testuser', password='password')
        
        response = self.client.post(
            reverse('rewards'),
            {
                f'reward_quantity_{self.reward1.id}': '1',
                f'reward_quantity_{self.reward2.id}': '2'
            },
            follow=True
        )
        
        assert response.status_code == 200
        
        # Check that a request was created
        request = RewardRequest.objects.filter(user=self.user).first()
        assert request is not None
        assert request.rewardrequestitem_set.count() == 2
        assert request.total_points == 500 + (2 * 300) == 1100
    
    def test_rewards_view_post_zero_quantity(self):
        self.client.login(username='testuser', password='password')
        
        response = self.client.post(
            reverse('rewards'),
            {
                f'reward_quantity_{self.reward1.id}': '0',
                f'reward_quantity_{self.reward2.id}': '0'
            },
            follow=True
        )
        
        assert response.status_code == 200
        
        # Check that a request was created but with no items
        request = RewardRequest.objects.filter(user=self.user).first()
        assert request is not None
        assert request.rewardrequestitem_set.count() == 0
        assert request.total_points == 0


@pytest.mark.django_db
class TestRewardsRequestConfirmationView:
    def setup_method(self):
        self.user = User.objects.create_user(
            username="testuser",
            password="password",
            user_number="12345",
            user_phone="1234567890"
        )
        
        self.brand = Brand.objects.create(
            name="Test Brand",
            prefix="TB"
        )
        
        # Create rewards
        self.reward = Reward.objects.create(
            abra_code="TB001",
            name="Test Reward",
            point_cost=500,
            description="Test description",
            brand=self.brand,
            is_active=True
        )
        
        # Add some points
        PointsTransaction.objects.create(
            user=self.user,
            value=1000,
            date=timezone.now().date(),
            description="Test transaction",
            type="STANDARD_POINTS",
            status="CONFIRMED"
        )
        
        # Create a reward request
        self.request = RewardRequest.objects.create(
            user=self.user,
            status="DRAFT",
            description="Test request"
        )
        
        # Add items to the request
        self.request_item = RewardRequestItem.objects.create(
            reward_request=self.request,
            reward=self.reward,
            quantity=1
        )
        
        # Save to calculate total points
        self.request.save()
        
        self.client = Client()
    
    def test_rewards_request_confirmation_view_get(self):
        self.client.login(username='testuser', password='password')
        
        response = self.client.get(
            reverse('rewards_request_detail', kwargs={'pk': self.request.id})
        )
        
        assert response.status_code == 200
        assert 'request' in response.context
        assert response.context['request'] == self.request
        assert 'items' in response.context
        assert len(response.context['items']) == 1
        assert 'user_balance' in response.context
        assert response.context['user_balance'] == 1000
    
    def test_rewards_request_confirmation_view_post(self):
        self.client.login(username='testuser', password='password')
        
        response = self.client.post(
            reverse('rewards_request_detail', kwargs={'pk': self.request.id}),
            follow=True
        )
        
        assert response.status_code == 200
        
        # Refresh the request
        self.request.refresh_from_db()
        
        # Check status change
        assert self.request.status == "PENDING"
        
        # Check transaction creation
        transaction = PointsTransaction.objects.filter(
            user=self.user,
            type="REWARD_CLAIM",
            reward_request=self.request
        ).first()
        
        assert transaction is not None
        assert transaction.value == -500  # Negative points
        assert transaction.status == "CONFIRMED"
        
        # Check user balance
        assert self.user.get_balance() == 500  # 1000 - 500
