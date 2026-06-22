from django.db import models


class NotificationKind(models.TextChoices):
    ESCALATION = "ESCALATION", "Escalation Alert"
    INTELLIGENCE_COMPLETE = "INTELLIGENCE_COMPLETE", "AI Query Complete"
    WORKFLOW_UPDATE = "WORKFLOW_UPDATE", "Workflow Update"
    GENERAL = "GENERAL", "General"
