FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install python deps sequentially to save RAM/Space
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Run Celery and Uvicorn in one container
CMD ["sh", "-c", "celery -A shared.messaging.CeleryApp:celery_app worker -l info & uvicorn Main:App --host 0.0.0.0 --port 8000"]
