FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
COPY requirements.docker.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements.docker.txt

COPY . .

ENV MODEL_DIR=/app/models

EXPOSE 8000

# Default to Django runserver for development; compose overrides with migrate + runserver
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
