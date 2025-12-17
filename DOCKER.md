# Docker (development)

This repository includes a development-friendly Docker setup that runs the Django web app, a Celery worker (TensorFlow CPU image), and Redis as the broker.

Quick start (from the project root):

```powershell
# build and start services
docker-compose up --build

# the compose `web` service runs migrations automatically on start

# (optional) create superuser
docker-compose run --rm web python manage.py createsuperuser
```

Notes:
- The `models/` directory is mounted into the containers at `/app/models`. Put your `.h5` model files there.
- The `worker` service uses `tensorflow/tensorflow:2.13.0` for CPU inference. If/when you need GPU inference, we'll switch to a GPU-enabled base image and configure the runtime.
- Environment variables are read from `.env`. Copy `.env.example` to `.env` and edit as needed.
