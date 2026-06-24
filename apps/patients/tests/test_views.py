from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.constants import HospitalType
from apps.core.models import Hospital
from apps.patients.constants import Gender
from apps.patients.models import Admission, Bed, Patient, Ward
from apps.patients.services import admit_patient
from apps.users.constants import UserRole

User = get_user_model()

# --------------- helpers ---------------

def make_hospital(name="City Hospital"):
    return Hospital.all_objects.create(
        name=name, type=HospitalType.PRIVATE_SINGLE,
        city="Mumbai", state="Maharashtra", bed_count=100,
    )


def make_user(username, role=UserRole.WARD_STAFF, hospital=None, password="Pass1234!"):
    return User.objects.create_user(
        username=username, password=password, role=role, hospital=hospital,
    )


def make_patient(hospital, mrn="MRN001"):
    return Patient.objects.create(
        mrn=mrn, first_name="Anita", last_name="Rao",
        date_of_birth="1990-06-15", gender=Gender.FEMALE,
        hospital=hospital,
    )


def make_ward(hospital, name="Ward A"):
    return Ward.objects.create(name=name, hospital=hospital, capacity=10)


def make_bed(ward, number="B1"):
    return Bed.objects.create(number=number, ward=ward)


def auth_client(user):
    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


# --------------- Patient list/create ---------------

class TestPatientListView(APITestCase):
    url = "/api/v1/patients/"

    def setUp(self):
        self.hospital = make_hospital()
        self.user = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.client = auth_client(self.user)
        make_patient(self.hospital, "MRN001")
        make_patient(self.hospital, "MRN002")

    def test_lists_patients_for_own_hospital(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)

    def test_does_not_return_other_hospital_patients(self):
        h2 = make_hospital("Other Hospital")
        make_patient(h2, "MRN-H2")
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["count"], 2)

    def test_unauthenticated_returns_401(self):
        resp = self.client_class().get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_search_by_mrn(self):
        resp = self.client.get(self.url, {"search": "MRN001"})
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["mrn"], "MRN001")

    def test_status_filter_active(self):
        nurse = make_user("nurse_x", UserRole.NURSE, self.hospital)
        p = make_patient(self.hospital, "MRN003")
        ward = make_ward(self.hospital)
        bed = make_bed(ward)
        admit_patient(user=nurse, patient=p, bed=bed)
        resp = self.client.get(self.url, {"status": "active"})
        mrns = [r["mrn"] for r in resp.data["results"]]
        self.assertIn("MRN003", mrns)
        self.assertNotIn("MRN001", mrns)


class TestPatientCreateView(APITestCase):
    url = "/api/v1/patients/"

    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.ward_staff = make_user("staff1", UserRole.WARD_STAFF, self.hospital)

    def test_admin_can_create_patient(self):
        client = auth_client(self.admin)
        resp = client.post(self.url, {
            "mrn": "NEW001",
            "first_name": "Rahul",
            "last_name": "Mehta",
            "date_of_birth": "1988-03-10",
            "gender": "MALE",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["mrn"], "NEW001")

    def test_ward_staff_gets_403(self):
        client = auth_client(self.ward_staff)
        resp = client.post(self.url, {
            "mrn": "NEW002",
            "first_name": "A",
            "last_name": "B",
            "date_of_birth": "1990-01-01",
            "gender": "MALE",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_mrn_returns_409(self):
        make_patient(self.hospital, "MRN-DUP")
        client = auth_client(self.admin)
        resp = client.post(self.url, {
            "mrn": "MRN-DUP",
            "first_name": "A",
            "last_name": "B",
            "date_of_birth": "1990-01-01",
            "gender": "MALE",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    def test_missing_required_field_returns_400(self):
        client = auth_client(self.admin)
        resp = client.post(self.url, {"mrn": "NEW003"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# --------------- Patient detail ---------------

class TestPatientDetailView(APITestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.nurse = make_user("nurse2", UserRole.NURSE, self.hospital)
        self.admin = make_user("admin2", UserRole.ADMIN, self.hospital)
        self.ward_staff = make_user("staff2", UserRole.WARD_STAFF, self.hospital)
        self.patient = make_patient(self.hospital)
        self.url = f"/api/v1/patients/{self.patient.pk}/"

    def test_get_returns_patient(self):
        resp = auth_client(self.nurse).get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["mrn"], "MRN001")

    def test_get_nonexistent_returns_404(self):
        resp = auth_client(self.nurse).get("/api/v1/patients/99999/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_other_hospital_patient_returns_404(self):
        h2 = make_hospital("Other")
        p2 = make_patient(h2, "MRN-H2")
        resp = auth_client(self.nurse).get(f"/api/v1/patients/{p2.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_nurse_can_patch(self):
        resp = auth_client(self.nurse).patch(self.url, {"blood_group": "O+"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["blood_group"], "O+")

    def test_ward_staff_patch_returns_403(self):
        resp = auth_client(self.ward_staff).patch(self.url, {"blood_group": "A+"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_delete(self):
        resp = auth_client(self.admin).delete(self.url)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Patient.objects.filter(pk=self.patient.pk).exists())

    def test_nurse_delete_returns_403(self):
        resp = auth_client(self.nurse).delete(self.url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


# --------------- Admit / Discharge ---------------

class TestAdmitDischargeViews(APITestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.nurse = make_user("nurse3", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.ward = make_ward(self.hospital)
        self.bed = make_bed(self.ward)
        self.admit_url = f"/api/v1/patients/{self.patient.pk}/admit/"
        self.discharge_url = f"/api/v1/patients/{self.patient.pk}/discharge/"

    def test_admit_without_bed(self):
        resp = auth_client(self.nurse).post(self.admit_url, {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resp.data["is_active"])

    def test_admit_with_bed(self):
        resp = auth_client(self.nurse).post(self.admit_url, {"bed": self.bed.pk}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["bed"], self.bed.pk)
        self.bed.refresh_from_db()
        self.assertTrue(self.bed.is_occupied)

    def test_admit_already_admitted_returns_400(self):
        auth_client(self.nurse).post(self.admit_url, {}, format="json")
        resp = auth_client(self.nurse).post(self.admit_url, {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admit_occupied_bed_returns_409(self):
        self.bed.is_occupied = True
        self.bed.save()
        resp = auth_client(self.nurse).post(self.admit_url, {"bed": self.bed.pk}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    def test_discharge_active_admission(self):
        auth_client(self.nurse).post(self.admit_url, {}, format="json")
        resp = auth_client(self.nurse).post(self.discharge_url, {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["is_active"])

    def test_discharge_not_admitted_returns_400(self):
        resp = auth_client(self.nurse).post(self.discharge_url, {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admission_history(self):
        admit_url = self.admit_url
        auth_client(self.nurse).post(admit_url, {}, format="json")
        auth_client(self.nurse).post(self.discharge_url, {}, format="json")
        resp = auth_client(self.nurse).get(f"/api/v1/patients/{self.patient.pk}/admissions/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)


# --------------- Ward / Bed ---------------

class TestWardBedsViews(APITestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.user = make_user("staff3", UserRole.WARD_STAFF, self.hospital)
        self.ward = make_ward(self.hospital)
        make_bed(self.ward, "B1")
        make_bed(self.ward, "B2")

    def test_list_wards(self):
        resp = auth_client(self.user).get("/api/v1/wards/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["name"], "Ward A")

    def test_list_wards_scoped_to_hospital(self):
        h2 = make_hospital("Other")
        make_ward(h2, "Ward X")
        resp = auth_client(self.user).get("/api/v1/wards/")
        names = [w["name"] for w in resp.data]
        self.assertNotIn("Ward X", names)

    def test_list_beds_for_ward(self):
        resp = auth_client(self.user).get(f"/api/v1/wards/{self.ward.pk}/beds/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 2)

    def test_ward_from_other_hospital_returns_404(self):
        h2 = make_hospital("Other")
        ward2 = make_ward(h2, "Ward Y")
        resp = auth_client(self.user).get(f"/api/v1/wards/{ward2.pk}/beds/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_ward_returns_401(self):
        resp = self.client_class().get("/api/v1/wards/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# --------------- Ward CRUD ---------------

class TestWardCRUD(APITestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin_wc", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse_wc", UserRole.NURSE, self.hospital)

    def test_admin_can_create_ward(self):
        resp = auth_client(self.admin).post("/api/v1/wards/", {"name": "ICU", "capacity": 20})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["name"], "ICU")
        self.assertEqual(resp.data["capacity"], 20)

    def test_nurse_cannot_create_ward(self):
        resp = auth_client(self.nurse).post("/api/v1/wards/", {"name": "ICU", "capacity": 20})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_ward_missing_capacity(self):
        resp = auth_client(self.admin).post("/api/v1/wards/", {"name": "ICU"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_can_retrieve_ward(self):
        ward = make_ward(self.hospital)
        resp = auth_client(self.admin).get(f"/api/v1/wards/{ward.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["name"], ward.name)

    def test_admin_can_update_ward(self):
        ward = make_ward(self.hospital)
        resp = auth_client(self.admin).patch(f"/api/v1/wards/{ward.pk}/", {"name": "Ward Updated", "capacity": 15})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["name"], "Ward Updated")

    def test_update_ward_wrong_hospital_returns_404(self):
        h2 = make_hospital("Other")
        ward2 = make_ward(h2, "Other Ward")
        resp = auth_client(self.admin).patch(f"/api/v1/wards/{ward2.pk}/", {"name": "X"})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_delete_ward(self):
        ward = make_ward(self.hospital)
        resp = auth_client(self.admin).delete(f"/api/v1/wards/{ward.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Ward.objects.filter(pk=ward.pk).exists())

    def test_delete_ward_with_occupied_bed_returns_400(self):
        ward = make_ward(self.hospital)
        bed = make_bed(ward, "B1")
        bed.is_occupied = True
        bed.save()
        resp = auth_client(self.admin).delete(f"/api/v1/wards/{ward.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nurse_cannot_delete_ward(self):
        ward = make_ward(self.hospital)
        resp = auth_client(self.nurse).delete(f"/api/v1/wards/{ward.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


# --------------- Bed CRUD ---------------

class TestBedCRUD(APITestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin_bc", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse_bc", UserRole.NURSE, self.hospital)
        self.ward = make_ward(self.hospital)

    def test_admin_can_add_bed_to_ward(self):
        resp = auth_client(self.admin).post(f"/api/v1/wards/{self.ward.pk}/beds/", {"number": "101"})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["number"], "101")

    def test_duplicate_bed_number_returns_409(self):
        make_bed(self.ward, "101")
        resp = auth_client(self.admin).post(f"/api/v1/wards/{self.ward.pk}/beds/", {"number": "101"})
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    def test_nurse_cannot_add_bed(self):
        resp = auth_client(self.nurse).post(f"/api/v1/wards/{self.ward.pk}/beds/", {"number": "101"})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_add_bed_wrong_hospital_returns_404(self):
        h2 = make_hospital("Other")
        ward2 = make_ward(h2)
        resp = auth_client(self.admin).post(f"/api/v1/wards/{ward2.pk}/beds/", {"number": "101"})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_update_bed_number(self):
        bed = make_bed(self.ward, "B1")
        resp = auth_client(self.admin).patch(f"/api/v1/beds/{bed.pk}/", {"number": "B1-Updated"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["number"], "B1-Updated")

    def test_admin_can_delete_bed(self):
        bed = make_bed(self.ward, "B99")
        resp = auth_client(self.admin).delete(f"/api/v1/beds/{bed.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Bed.objects.filter(pk=bed.pk).exists())

    def test_delete_occupied_bed_returns_400(self):
        bed = make_bed(self.ward, "B99")
        bed.is_occupied = True
        bed.save()
        resp = auth_client(self.admin).delete(f"/api/v1/beds/{bed.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bed_from_other_hospital_returns_404(self):
        h2 = make_hospital("Other")
        ward2 = make_ward(h2)
        bed2 = make_bed(ward2, "B1")
        resp = auth_client(self.admin).delete(f"/api/v1/beds/{bed2.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_nurse_cannot_delete_bed(self):
        bed = make_bed(self.ward, "B1")
        resp = auth_client(self.nurse).delete(f"/api/v1/beds/{bed.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
