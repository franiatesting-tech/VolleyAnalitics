"""Celery task name constants shared between services/api (enqueues by
name) and services/worker (registers the task under this exact name).
Two independent string literals that happen to match is how tasks silently
stop routing after one side is renamed -- this is the single source of
truth for that name.
"""

PROCESS_DEMO_MATCH_TASK_NAME = "process_demo_match"
