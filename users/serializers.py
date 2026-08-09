from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.db import models
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from .models import Branch, UserRoleAssignment

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user profile"""
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'phone_number', 'full_name', 'gender',
            'profile_picture', 'is_student', 'is_teacher',
            'status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SignupSerializer(serializers.ModelSerializer):
    """Serializer for user registration"""
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, required=True)
    
    class Meta:
        model = User
        fields = ['email', 'password', 'password_confirm', 'phone_number', 'full_name', 'gender']
    
    def validate_email(self, value):
        """Ensure email is unique"""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value
    
    def validate(self, attrs):
        """Validate password confirmation"""
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs
    
    def create(self, validated_data):
        """Create user with hashed password"""
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        return user


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom JWT token serializer with user data"""
    
    def validate(self, attrs):
        data = super().validate(attrs)
        
        # Add user data to response
        data['user'] = UserSerializer(self.user).data
        
        return data


class LoginSerializer(serializers.Serializer):
    """Serializer for user login via email"""
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            # Find user by email
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                raise serializers.ValidationError('Unable to log in with provided credentials.')
            
            # Check password
            if not user.check_password(password):
                raise serializers.ValidationError('Unable to log in with provided credentials.')
            
            if not user.is_active:
                raise serializers.ValidationError('User account is disabled.')
            
            attrs['user'] = user
            return attrs
        else:
            raise serializers.ValidationError('Must include "email" and "password".')


class LogoutSerializer(serializers.Serializer):
    """Serializer for logout request"""
    refresh_token = serializers.CharField(required=True, help_text="Refresh token to blacklist")


class BranchSerializer(serializers.ModelSerializer):
    """Serializer for Branch"""
    
    class Meta:
        model = Branch
        fields = ['id', 'name', 'short_name', 'address', 'latitude', 'longitude']


class PermissionSerializer(serializers.ModelSerializer):
    """Serializer for Django Permission"""
    
    class Meta:
        model = Permission
        fields = ['id', 'name', 'codename', 'content_type']


class GroupSerializer(serializers.ModelSerializer):
    """Serializer for Django Group (Role)"""
    permissions = PermissionSerializer(many=True, read_only=True)
    
    class Meta:
        model = Group
        fields = ['id', 'name', 'permissions']


class RoleAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for user role assignments with branch scope"""
    role = GroupSerializer(source='group', read_only=True)
    branch = BranchSerializer(read_only=True)
    
    class Meta:
        model = UserRoleAssignment
        fields = ['id', 'role', 'branch', 'assigned_at']


class UserRolesSerializer(serializers.Serializer):
    """Serializer for user's effective roles"""
    roles = RoleAssignmentSerializer(many=True, source='role_assignments')
    global_groups = serializers.SerializerMethodField()
    
    @extend_schema_field(GroupSerializer(many=True))
    def get_global_groups(self, obj):
        """Get user's direct group assignments (non-branch-scoped)"""
        return GroupSerializer(obj.groups.all(), many=True).data
    
    class Meta:
        fields = ['roles', 'global_groups']


class UserPermissionsSerializer(serializers.Serializer):
    """Serializer for user's effective permissions"""
    permissions = serializers.SerializerMethodField()
    
    @extend_schema_field(PermissionSerializer(many=True))
    def get_permissions(self, obj):
        """Get all permissions from user's roles and groups"""
        permissions = set()
        
        # Get permissions from direct groups
        for group in obj.groups.all():
            permissions.update(group.permissions.all())
        
        # Get permissions from role assignments
        branch_id = self.context.get('branch_id')
        role_assignments = obj.role_assignments.all()
        
        if branch_id:
            # Filter by specific branch or global roles
            role_assignments = role_assignments.filter(
                models.Q(branch_id=branch_id) | models.Q(branch__isnull=True)
            )
        
        for assignment in role_assignments:
            permissions.update(assignment.group.permissions.all())
        
        # Get user-specific permissions
        permissions.update(obj.user_permissions.all())
        
        return PermissionSerializer(list(permissions), many=True).data
