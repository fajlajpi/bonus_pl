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
    FileUpload, Reward, RewardRequest, RewardRequestItem, create_manager_group_and_permissions
)
from pa_bonus.views import (
    upload_file, upload_history, DashboardView, HistoryView,
    RewardsView, RewardsRequestConfirmationView
)
from pa_bonus.tasks import process_uploaded_file
from pa_bonus.forms import FileUploadForm

# Model Tests
@pytest.mark.django_db
class TestUserModel:
    def test_user_creation(self):
        user = User.objects.create(
            username="testuser",
            email="test@example.com",
            user_number="12345",
            user_phone="1234567890"
        )
        assert user.username == "testuser"
        assert user.user_number == "12345"
        assert user.user_phone == "1234567890"
        
    def test_user_str_representation(self):
        user = User.objects.create(
            username="testuser",
            first_name="Test",
            last_name="User",
            user_number="12345",
            user_phone="1234567890"
        )
        assert str(user) == "testuser | Test User"
    
    def test_get_balance_with_transactions(self):
        user = User.objects.create(
            username="testuser",
            user_number="12345",
            user_phone="1234567890"
        )
        
        # Create transactions
        PointsTransaction.objects.create(
            user=user,
            value=100,
            date=timezone.now().date(),
            description="Test transaction 1",
            type="STANDARD_POINTS",
            status="CONFIRMED"
        )
        
        PointsTransaction.objects.create(
            user=user,
            value=50,
            date=timezone.now().date(),
            description="Test transaction 2",
            type="STANDARD_POINTS",
            status="CONFIRMED"
        )
        
        PointsTransaction.objects.create(
            user=user,
            value=-25,
            date=timezone.now().date(),
            description="Test transaction 3",
            type="REWARD_CLAIM",
            status="CONFIRMED"
        )
        
        # Non-confirmed transaction shouldn't be counted
        PointsTransaction.objects.create(
            user=user,
            value=200,
            date=timezone.now().date(),
            description="Pending transaction",
            type="STANDARD_POINTS",
            status="PENDING"
        )
        
        assert user.get_balance() == 125  # 100 + 50 - 25

    def test_get_balance_no_transactions(self):
        user = User.objects.create(
            username="testuser",
            user_number="12345",
            user_phone="1234567890"
        )
        assert user.get_balance() == 0


@pytest.mark.django_db
class TestBrandModel:
    def test_brand_creation(self):
        brand = Brand.objects.create(
            name="Test Brand",
            prefix="TB"
        )
        assert brand.name == "Test Brand"
        assert brand.prefix == "TB"
    
    def test_brand_str_representation(self):
        brand = Brand.objects.create(
            name="Test Brand",
            prefix="TB"
        )
        assert str(brand) == "Test Brand"


@pytest.mark.django_db
class TestUserContract:
    def setup_method(self):
        self.user = User.objects.create(
            username="testuser",
            user_number="12345",
            user_phone="1234567890",
            first_name="Test",
            last_name="User"
        )
        
        self.brand = Brand.objects.create(
            name="Test Brand",
            prefix="TB"
        )
        
        self.brand_bonus = BrandBonus.objects.create(
            name="Test Bonus",
            points_ratio=1.5,
            brand_id=self.brand
        )
        
    def test_contract_creation(self):
        contract = UserContract.objects.create(
            user_id=self.user,
            contract_date_from=date.today(),
            contract_date_to=date.today() + timedelta(days=365),
            is_active=True
        )
        contract.brandbonuses.add(self.brand_bonus)
        
        assert contract.user_id == self.user
        assert contract.is_active == True
        assert contract.brandbonuses.count() == 1
        assert contract.brandbonuses.first() == self.brand_bonus
    
    def test_contract_str_representation(self):
        contract = UserContract.objects.create(
            user_id=self.user,
            contract_date_from=date.today(),
            contract_date_to=date.today() + timedelta(days=365),
            is_active=True
        )
        
        expected_str = f"User Test ({date.today()})"
        assert str(contract) == expected_str


@pytest.mark.django_db
class TestFileUploadModel:
    def setup_method(self):
        self.user = User.objects.create(
            username="testuser",
            user_number="12345",
            user_phone="1234567890"
        )
    
    def test_file_upload_creation(self):
        file_upload = FileUpload.objects.create(
            file="test.csv",
            status="PENDING",
            uploaded_by=self.user
        )
        
        assert file_upload.status == "PENDING"
        assert file_upload.uploaded_by == self.user
    
    def test_file_upload_str_representation(self):
        file_upload = FileUpload.objects.create(
            file="test.csv",
            status="PENDING",
            uploaded_by=self.user
        )
        
        assert str(file_upload).startswith(f"Upload {file_upload.id} | {file_upload.uploaded_at} | PENDING | by {self.user}")


@pytest.mark.django_db
class TestRewardRelatedModels:
    def setup_method(self):
        self.user = User.objects.create(
            username="testuser",
            user_number="12345",
            user_phone="1234567890"
        )
        
        self.brand = Brand.objects.create(
            name="Test Brand",
            prefix="TB"
        )
        
    def test_reward_creation(self):
        reward = Reward.objects.create(
            abra_code="TB001",
            name="Test Reward",
            point_cost=500,
            description="Test description",
            brand=self.brand,
            is_active=True
        )
        
        assert reward.abra_code == "TB001"
        assert reward.name == "Test Reward"
        assert reward.point_cost == 500
        assert reward.brand == self.brand
    
    def test_reward_str_representation(self):
        reward = Reward.objects.create(
            abra_code="TB001",
            name="Test Reward",
            point_cost=500,
            description="Test description",
            brand=self.brand,
            is_active=True
        )
        
        assert str(reward) == "TB | Test Reward"
    
    def test_reward_request_creation(self):
        request = RewardRequest.objects.create(
            user=self.user,
            status="DRAFT",
            description="Test request"
        )
        
        assert request.user == self.user
        assert request.status == "DRAFT"
        assert request.total_points == 0
    
    def test_reward_request_items_and_total_calculation(self):
        request = RewardRequest.objects.create(
            user=self.user,
            status="DRAFT",
            description="Test request"
        )
        
        reward1 = Reward.objects.create(
            abra_code="TB001",
            name="Test Reward 1",
            point_cost=500,
            description="Test description 1",
            brand=self.brand,
            is_active=True
        )
        
        reward2 = Reward.objects.create(
            abra_code="TB002",
            name="Test Reward 2",
            point_cost=300,
            description="Test description 2",
            brand=self.brand,
            is_active=True
        )
        
        request_item1 = RewardRequestItem.objects.create(
            reward_request=request,
            reward=reward1,
            quantity=2
        )
        
        request_item2 = RewardRequestItem.objects.create(
            reward_request=request,
            reward=reward2,
            quantity=1
        )
        
        # Refresh request to get updated total_points
        request.refresh_from_db()

        # Call the save() function to update total_points
        request.save()
        
        assert request_item1.point_cost == 500
        assert request_item2.point_cost == 300
        assert request.total_points == (2 * 500) + (1 * 300) == 1300