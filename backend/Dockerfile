FROM python:3.11-slim
WORKDIR /app/backend
COPY pyproject.toml ./
COPY requirements-dev.lock.txt ./
RUN --mount=type=cache,target=/root/.cache/pip python -c "import subprocess,tomllib; subprocess.check_call(['pip','install','-c','requirements-dev.lock.txt',*tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']])"
COPY app ./app
COPY evals ./evals
COPY alembic.ini ./
COPY alembic ./alembic
RUN pip install --no-cache-dir --no-deps .
RUN useradd --create-home bankai
USER bankai
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
