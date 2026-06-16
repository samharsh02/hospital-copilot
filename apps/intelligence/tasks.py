from config.celery import app


@app.task(bind=True, max_retries=2)
def run_ai_query_task(self, request_id: int):
    from apps.intelligence.services import mark_request_failed, run_ai_query
    try:
        run_ai_query(request_id)
    except Exception as exc:
        try:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries * 60)
        except Exception:
            # MaxRetriesExceededError — mark the request as permanently failed.
            mark_request_failed(request_id)
