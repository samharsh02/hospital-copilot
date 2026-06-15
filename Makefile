PYTHON = .venv/bin/python
MANAGE = $(PYTHON) manage.py

.PHONY: run migrate migrations shell test lint typecheck seed

run:
	$(MANAGE) runserver

migrate:
	$(MANAGE) migrate

migrations:
	$(MANAGE) makemigrations

shell:
	$(MANAGE) shell_plus

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .

typecheck:
	.venv/bin/mypy .

seed:
	$(MANAGE) seed_data

worker:
	.venv/bin/celery -A celery worker --loglevel=info

beat:
	.venv/bin/celery -A celery beat --loglevel=info
