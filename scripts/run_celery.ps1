# Helper script to run the celery worker in development (PowerShell)
# Requires that Redis is running at 127.0.0.1:6379

Write-Host "Starting Celery worker..."
celery -A MedMind_Backend worker --loglevel=info
