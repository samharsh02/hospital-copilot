from typing import Optional

from django.conf import settings
from django.db import models
from django.utils.timezone import now

from apps.core.constants import HospitalType


class ActiveManager(models.Manager):
    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset().filter(is_deleted=False)


class BaseMixin(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )

    class Meta:
        abstract = True


class SoftDeleteMixin(models.Model):
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self, user: Optional[object] = None) -> None:
        self.is_deleted = True
        self.deleted_at = now()
        self.deleted_by = user
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])


class Hospital(BaseMixin, SoftDeleteMixin):
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=HospitalType.choices)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    bed_count = models.IntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "hospitals"

    def __str__(self) -> str:
        return self.name
