FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.web.txt ./
COPY requirements.docker.txt ./

# Increase pip timeout and retries to tolerate slow network during docker builds
ENV PIP_DEFAULT_TIMEOUT=120
RUN pip install -r requirements.web.txt -r requirements.docker.txt

COPY . .

ENV MODEL_DIR=/app/models

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
