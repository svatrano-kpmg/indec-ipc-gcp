FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Certificados y zona horaria
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Exponer puerto esperado por Cloud Run
ENV PORT=8080

# Entry para functions_framework: app=main.py, target=run_indec_downloader
CMD exec functions-framework \
    --target=run_indec_downloader \
    --port=$PORT \
    --signature-type=http
