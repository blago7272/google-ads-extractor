FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DBT_PROJECT_DIR=/app \
    DBT_PROFILES_DIR=/app/profiles

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

CMD ["python", "scripts/release_orchestrator.py"]
