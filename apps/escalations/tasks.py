from config.celery import app


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def evaluate_escalation_rules_task(self, admission_id: int):
    from apps.escalations.services import evaluate_escalation_rules
    try:
        evaluate_escalation_rules(admission_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 60)
