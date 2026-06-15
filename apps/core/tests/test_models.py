from django.db import models
from django.test import TestCase
from django.utils.timezone import now

from apps.core.models import ActiveManager, BaseMixin, SoftDeleteMixin

# Concrete model used to exercise the abstract mixins.
# Defined at module level so --no-migrations syncdb creates the table automatically.
class _Record(BaseMixin, SoftDeleteMixin):
    label = models.CharField(max_length=50)

    class Meta:
        app_label = "core"


class TestBaseMixinStructure:
    def test_is_abstract(self):
        assert BaseMixin._meta.abstract is True

    def test_has_created_at_field(self):
        field_names = [f.name for f in BaseMixin._meta.fields]
        assert "created_at" in field_names

    def test_has_updated_at_field(self):
        field_names = [f.name for f in BaseMixin._meta.fields]
        assert "updated_at" in field_names

    def test_has_created_by_field(self):
        field_names = [f.name for f in BaseMixin._meta.get_fields()]
        assert "created_by" in field_names

    def test_has_updated_by_field(self):
        field_names = [f.name for f in BaseMixin._meta.get_fields()]
        assert "updated_by" in field_names


class TestSoftDeleteMixinStructure:
    def test_is_abstract(self):
        assert SoftDeleteMixin._meta.abstract is True

    def test_has_is_deleted_field(self):
        field_names = [f.name for f in SoftDeleteMixin._meta.fields]
        assert "is_deleted" in field_names

    def test_has_deleted_at_field(self):
        field_names = [f.name for f in SoftDeleteMixin._meta.fields]
        assert "deleted_at" in field_names

    def test_has_deleted_by_field(self):
        field_names = [f.name for f in SoftDeleteMixin._meta.get_fields()]
        assert "deleted_by" in field_names

    def test_has_soft_delete_method(self):
        assert callable(getattr(SoftDeleteMixin, "soft_delete", None))

    def test_default_manager_is_active_manager(self):
        manager_by_name = {m.name: m for m in SoftDeleteMixin._meta.managers}
        assert "objects" in manager_by_name
        assert isinstance(manager_by_name["objects"], ActiveManager)

    def test_has_all_objects_manager(self):
        manager_names = [m.name for m in SoftDeleteMixin._meta.managers]
        assert "all_objects" in manager_names

    def test_is_deleted_defaults_to_false(self):
        field = SoftDeleteMixin._meta.get_field("is_deleted")
        assert field.default is False

    def test_is_deleted_has_db_index(self):
        field = SoftDeleteMixin._meta.get_field("is_deleted")
        assert field.db_index is True


class TestSoftDeleteBehaviour(TestCase):
    def test_soft_delete_sets_is_deleted_to_true(self):
        instance = _Record.all_objects.create(label="test")
        instance.soft_delete()
        instance.refresh_from_db()
        self.assertTrue(instance.is_deleted)

    def test_soft_delete_sets_deleted_at_timestamp(self):
        instance = _Record.all_objects.create(label="test")
        before = now()
        instance.soft_delete()
        instance.refresh_from_db()
        self.assertIsNotNone(instance.deleted_at)
        self.assertGreaterEqual(instance.deleted_at, before)

    def test_soft_delete_accepts_none_user(self):
        instance = _Record.all_objects.create(label="test")
        instance.soft_delete(user=None)
        instance.refresh_from_db()
        self.assertIsNone(instance.deleted_by)

    def test_active_manager_excludes_soft_deleted_records(self):
        _Record.all_objects.create(label="visible")
        hidden = _Record.all_objects.create(label="hidden")
        hidden.soft_delete()

        active_labels = list(_Record.objects.values_list("label", flat=True))
        self.assertIn("visible", active_labels)
        self.assertNotIn("hidden", active_labels)

    def test_all_objects_includes_soft_deleted_records(self):
        _Record.all_objects.create(label="visible")
        hidden = _Record.all_objects.create(label="hidden")
        hidden.soft_delete()

        all_labels = list(_Record.all_objects.values_list("label", flat=True))
        self.assertIn("visible", all_labels)
        self.assertIn("hidden", all_labels)

    def test_soft_delete_does_not_hard_delete_row(self):
        instance = _Record.all_objects.create(label="test")
        instance.soft_delete()
        self.assertTrue(_Record.all_objects.filter(pk=instance.pk).exists())
