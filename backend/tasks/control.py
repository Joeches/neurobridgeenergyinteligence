"""
Compatibility bridge for Celery task discovery.

The production task implementation lives in:
backend.tasks.control_tasks

This file exists only to preserve older Celery import paths:
backend.tasks.control
"""

from backend.tasks.control_tasks import *  # noqa: F401,F403