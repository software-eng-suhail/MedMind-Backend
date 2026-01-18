# MedMind-Backend

## Running Celery with Redis (development)

This project uses Celery for background inference tasks. For development you can use Redis as the broker.

1) Start Redis using Docker (or install it locally):

```
docker run -d --name medmind-redis -p 6379:6379 redis:7
```

If Redis is on a different host, set the broker env var before starting Django and Celery:

```
setx CELERY_BROKER_URL "redis://<host>:6379/0"
```

2) Start Django dev server in one terminal:

```
python manage.py runserver 127.0.0.1:8000
```

3) Start the Celery worker in another terminal:

```
celery -A MedMind_Backend worker --loglevel=info
```

Installation (Python environment):

```
python -m pip install -r requirements.txt
```

4) Send a checkup POST as in `scripts/debug_request.py`.

Notes:
- The web process no longer requires TensorFlow; only the worker does.
- If you want tasks to run inline during development, set `CELERY_TASK_ALWAYS_EAGER=True` in environment or `settings.py`.