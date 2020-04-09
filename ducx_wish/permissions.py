from rest_framework import permissions
from django.contrib.auth.models import User

class _PermissionLogicMixin(permissions.BasePermission): 
    def _create_class(self, other, conj):
        class_name = self.__class__.__name__ + conj + other.__class__.__name__
        if self.__class__ is other.__class__:
            res = type(class_name, (self.__class__,), {})()
        else:
            res = type(class_name, (self.__class__, other.__class__), {})()
        return res 

    def __or__(self, other):
        res = self._create_class(other, 'Or')
        res.has_permission = self._or_has_permission(self, other)
        res.has_object_permission = self._or_has_object_permission(self, other)
        return res 

    def __and__(self, other):
        res = self._create_class(other, 'And')
        res.has_permission = self._and_has_permission(self, other)
        res.has_object_permission = self._and_has_object_permission(self, other)
        return res 

    def _or_has_permission(self, o1, o2):
        def real(*args):
            return o1.has_permission(*args) or o2.has_permission(*args)
        return real

    def _or_has_object_permission(self, o1, o2):
        def real(*args):
            return o1.has_object_permission(*args) or o2.has_object_permission(*args)
        return real

    def _and_has_permission(self, o1, o2):
        def real(*args):
            return o1.has_permission(*args) and o2.has_permission(*args)
        return real

    def _and_has_object_permission(self, o1, o2):
        def real(*args):
            return o1.has_object_permission(*args) and o2.has_object_permission(*args)
        return real

    def __call__(self, *args):
        return self


def permission_logic(cls):
    return type(cls.__name__, (cls, _PermissionLogicMixin), {})()

@permission_logic
class IsOwner(permissions.BasePermission):    
    def has_object_permission(self, request, view, obj):
        if isinstance(obj, User):
            return obj.id == request.user.id
        else:
            return obj.user == request.user

@permission_logic
class IsStaff(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.is_staff

    def has_permission(self, request, view):
        return request.user.is_staff

@permission_logic
class IsDucXAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.profile.is_ducx_admin

    def has_permission(self, request, view):
        return request.user.profile.is_ducx_admin

@permission_logic
class ReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.method in permissions.SAFE_METHODS

    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS


@permission_logic
class CreateOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.method == 'POST'

    def has_permission(self, request, view):
        return request.method == 'POST'

