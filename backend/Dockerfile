FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && if [ -f /app/local-data/outlets.csv ] && [ -f /app/local-data/vehicles.csv ]; then python -m app.seed; else echo 'Official datasets not mounted; starting without seed data.'; fi && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
