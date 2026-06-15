from django.db import models


class HospitalType(models.TextChoices):
    PRIVATE_SINGLE = "PRIVATE_SINGLE", "Private (Single)"
    PRIVATE_CHAIN = "PRIVATE_CHAIN", "Private (Chain)"
    GOVERNMENT = "GOVERNMENT", "Government"
    TRUST = "TRUST", "Trust"
