FROM python:3.11-slim
WORKDIR /app/backend
COPY pyproject.toml ./
COPY requirements-dev.lock.txt ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
RUN pip install --no-cache-dir -c requirements-dev.lock.txt .
RUN useradd --create-home bankai
USER bankai
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
