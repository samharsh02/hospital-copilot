from django.db import models


class WorkflowTrigger(models.TextChoices):
    ON_ADMIT = "ON_ADMIT", "On Admission"
    ON_DISCHARGE = "ON_DISCHARGE", "On Discharge"
    MANUAL = "MANUAL", "Manual"


class InstanceStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"
