from django.contrib import admin

from apps.patients.models import Admission, Bed, Patient, Ward


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ["mrn", "hospital", "gender", "is_active", "created_at"]
    list_filter = ["hospital", "gender", "is_active"]
    search_fields = ["mrn"]


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ["name", "hospital", "capacity"]
    list_filter = ["hospital"]


@admin.register(Bed)
class BedAdmin(admin.ModelAdmin):
    list_display = ["number", "ward", "is_occupied"]
    list_filter = ["ward__hospital", "is_occupied"]


@admin.register(Admission)
class AdmissionAdmin(admin.ModelAdmin):
    list_display = ["pk", "patient", "bed", "admitted_at", "discharged_at"]
    list_filter = ["patient__hospital"]
