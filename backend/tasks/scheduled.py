"""
Compatibility bridge for Celery scheduled task discovery.

Actual scheduled tasks are defined in:
- backend.tasks.energy_tasks
- backend.tasks.monitoring
- backend.tasks.weather_tasks
- backend.tasks.prediction_tasks
- backend.tasks.reporting
- backend.tasks.adfi
- backend.tasks.control_tasks
- backend.tasks.control

Celery beat schedule references concrete task names in other modules.
This file exists only to satisfy Celery's module discovery during startup.
"""

# Intentionally empty.
# The Celery include list has been updated to remove "backend.tasks.scheduled".
# If this file is still referenced, it serves as a no-op compatibility bridge.