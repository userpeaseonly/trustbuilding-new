import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient
from rest_framework import status
from users.models import Branch, UserRoleAssignment

User = get_user_model()


class AuthAPITestCase(TestCase):
    """Test authentication endpoints"""
    
    def setUp(self):
        self.client = APIClient()
        self.signup_url = '/api/auth/signup'
        self.login_url = '/api/auth/login'
        self.refresh_url = '/api/auth/refresh'
        self.logout_url = '/api/auth/logout'
        self.me_url = '/api/auth/me'
        
        self.user_data = {
            'email': 'test@example.com',
            'password': 'TestPass123!',
            'password_confirm': 'TestPass123!',
            'phone_number': '+998901234567',
            'full_name': 'Test User'
        }
    
    def test_signup_success(self):
        """Test user registration with valid data"""
        response = self.client.post(self.signup_url, self.user_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access_token', response.data)
        self.assertIn('refresh_token', response.data)
        self.assertIn('user', response.data)
        self.assertEqual(response.data['user']['email'], self.user_data['email'])
        
        # Verify user was created
        user = User.objects.get(email=self.user_data['email'])
        self.assertTrue(user.check_password(self.user_data['password']))
    
    def test_signup_duplicate_email(self):
        """Test signup with existing email fails"""
        # Create first user
        User.objects.create_user(
            email=self.user_data['email'],
            password=self.user_data['password']
        )
        
        # Try to create duplicate
        response = self.client.post(self.signup_url, self.user_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)
    
    def test_signup_password_mismatch(self):
        """Test signup with mismatched passwords fails"""
        data = self.user_data.copy()
        data['password_confirm'] = 'DifferentPass123!'
        
        response = self.client.post(self.signup_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)
    
    def test_signup_invalid_password(self):
        """Test signup with weak password fails"""
        data = self.user_data.copy()
        data['password'] = '123'
        data['password_confirm'] = '123'
        
        response = self.client.post(self.signup_url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_login_success(self):
        """Test login with valid credentials"""
        # Create user
        user = User.objects.create_user(
            email=self.user_data['email'],
            password=self.user_data['password']
        )
        
        # Login
        login_data = {
            'email': self.user_data['email'],
            'password': self.user_data['password']
        }
        response = self.client.post(self.login_url, login_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access_token', response.data)
        self.assertIn('refresh_token', response.data)
        self.assertIn('user', response.data)
    
    def test_login_invalid_credentials(self):
        """Test login with wrong password fails"""
        user = User.objects.create_user(
            email=self.user_data['email'],
            password=self.user_data['password']
        )
        
        login_data = {
            'email': self.user_data['email'],
            'password': 'WrongPassword123!'
        }
        response = self.client.post(self.login_url, login_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_refresh_token(self):
        """Test token refresh"""
        # Signup to get tokens
        response = self.client.post(self.signup_url, self.user_data, format='json')
        refresh_token = response.data['refresh_token']
        
        # Refresh token
        refresh_data = {'refresh': refresh_token}
        response = self.client.post(self.refresh_url, refresh_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
    
    def test_logout_success(self):
        """Test logout blacklists token"""
        # Signup to get tokens
        response = self.client.post(self.signup_url, self.user_data, format='json')
        access_token = response.data['access_token']
        refresh_token = response.data['refresh_token']
        
        # Set auth header
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        
        # Logout
        logout_data = {'refresh_token': refresh_token}
        response = self.client.post(self.logout_url, logout_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Try to use refresh token again (should fail)
        refresh_data = {'refresh': refresh_token}
        response = self.client.post(self.refresh_url, refresh_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_me_endpoint_authenticated(self):
        """Test /me endpoint returns user data"""
        # Create and login user
        response = self.client.post(self.signup_url, self.user_data, format='json')
        access_token = response.data['access_token']
        
        # Get /me
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        response = self.client.post(self.me_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], self.user_data['email'])
    
    def test_me_endpoint_unauthenticated(self):
        """Test /me endpoint requires authentication"""
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class RolesPermissionsAPITestCase(TestCase):
    """Test roles and permissions endpoints"""
    
    def setUp(self):
        self.client = APIClient()
        self.roles_url = '/api/auth/roles'
        self.permissions_url = '/api/auth/permissions'
        
        # Create user
        self.user = User.objects.create_user(
            email='test@example.com',
            password='TestPass123!',
            phone_number='+998901234567'
        )
        
        # Create branch
        self.branch = Branch.objects.create(name='Test Branch')
        
        # Create groups (roles)
        self.teacher_group = Group.objects.create(name='Teacher')
        self.manager_group = Group.objects.create(name='Manager')
        
        # Create permissions
        content_type = ContentType.objects.first()
        self.perm1 = Permission.objects.create(
            codename='view_students',
            name='Can view students',
            content_type=content_type
        )
        self.perm2 = Permission.objects.create(
            codename='add_students',
            name='Can add students',
            content_type=content_type
        )
        
        # Assign permissions to groups
        self.teacher_group.permissions.add(self.perm1)
        self.manager_group.permissions.add(self.perm1, self.perm2)
        
        # Authenticate
        self.client.force_authenticate(user=self.user)
    
    def test_roles_endpoint_no_roles(self):
        """Test roles endpoint with user having no roles"""
        response = self.client.get(self.roles_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['roles']), 0)
    
    def test_roles_endpoint_with_branch_role(self):
        """Test roles endpoint with branch-scoped role"""
        # Assign branch-scoped role
        UserRoleAssignment.objects.create(
            user=self.user,
            group=self.teacher_group,
            branch=self.branch
        )
        
        response = self.client.get(self.roles_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['roles']), 1)
        self.assertEqual(response.data['roles'][0]['role']['name'], 'Teacher')
        self.assertEqual(response.data['roles'][0]['branch']['name'], 'Test Branch')
    
    def test_roles_endpoint_with_global_role(self):
        """Test roles endpoint with global role (no branch)"""
        # Assign global role
        UserRoleAssignment.objects.create(
            user=self.user,
            group=self.manager_group,
            branch=None
        )
        
        response = self.client.get(self.roles_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['roles']), 1)
        self.assertEqual(response.data['roles'][0]['role']['name'], 'Manager')
        self.assertIsNone(response.data['roles'][0]['branch'])
    
    def test_permissions_endpoint(self):
        """Test permissions endpoint returns effective permissions"""
        # Assign role with permissions
        UserRoleAssignment.objects.create(
            user=self.user,
            group=self.teacher_group,
            branch=self.branch
        )
        
        response = self.client.get(self.permissions_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('permissions', response.data)
        
        # Check permissions list
        perm_codenames = [p['codename'] for p in response.data['permissions']]
        self.assertIn('view_students', perm_codenames)
    
    def test_permissions_endpoint_branch_filtered(self):
        """Test permissions can be filtered by branch"""
        # Assign branch-specific role
        UserRoleAssignment.objects.create(
            user=self.user,
            group=self.teacher_group,
            branch=self.branch
        )
        
        # Query with branch filter
        response = self.client.get(f'{self.permissions_url}?branch_id={self.branch.id}')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('permissions', response.data)
    
    def test_permissions_merge_multiple_roles(self):
        """Test permissions are merged from multiple roles"""
        # Assign multiple roles
        UserRoleAssignment.objects.create(
            user=self.user,
            group=self.teacher_group,
            branch=None
        )
        UserRoleAssignment.objects.create(
            user=self.user,
            group=self.manager_group,
            branch=self.branch
        )
        
        response = self.client.get(self.permissions_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        perm_codenames = [p['codename'] for p in response.data['permissions']]
        
        # Should have permissions from both roles
        self.assertIn('view_students', perm_codenames)
        self.assertIn('add_students', perm_codenames)
