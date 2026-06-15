from rest_framework.permissions import BasePermission

ROLE_RANK = {
    "WARD_STAFF": 1,
    "NURSE": 2,
    "DOCTOR": 3,
    "ADMIN": 4,
    "SUPERADMIN": 5,
}


def _make_role_perm(min_role: str):
    class _Perm(BasePermission):
        def has_permission(self, request, view):
            return (
                request.user
                and request.user.is_authenticated
                and ROLE_RANK.get(getattr(request.user, "role", ""), 0) >= ROLE_RANK[min_role]
            )
    _Perm.__name__ = f"Is{min_role.capitalize()}OrAbove"
    return _Perm


IsNurseOrAbove = _make_role_perm("NURSE")
IsAdminOrAbove = _make_role_perm("ADMIN")
