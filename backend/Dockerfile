# Use official Python image
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y curl

# Set workdir
WORKDIR /app

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Copy files
COPY pyproject.toml poetry.lock* /app/

# Install dependencies (no dev)
RUN poetry install --only main --no-root

# Copy app source code
COPY . /app

# Expose port
EXPOSE 8000

# Run FastAPI with uvicorn
CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
