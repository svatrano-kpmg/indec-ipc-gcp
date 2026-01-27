FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Certificados y zona horaria
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates tzdata \
 # agregado para usar CA del sistema   
 && update-ca-certificates \ 
 && rm -rf /var/lib/apt/lists/*

# Copio los certificados
COPY certificados/*.crt /usr/local/share/ca-certificates/

# Los registro
RUN update-ca-certificates

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
