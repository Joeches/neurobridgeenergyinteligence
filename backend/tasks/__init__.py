"""
NeuroBridge 11D - Celery Tasks Package
"""

# PRODUCTION TASK MODULES - EXCLUDE RESEARCH DOMAINS
PRODUCTION_TASK_MODULES = [
    'backend.tasks.energy_tasks',
    'backend.tasks.monitoring',
    'backend.tasks.weather_tasks',
    'backend.tasks.prediction_tasks',
    'backend.tasks.reporting',
    'backend.tasks.adfi',
]

# Filter out nuclear, fusion, quantum, defense
TASK_MODULES = [m for m in PRODUCTION_TASK_MODULES if not any(
    domain in m for domain in ['nuclear', 'fusion', 'quantum', 'defense']
)]