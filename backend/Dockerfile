FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Ensure curl_cffi (used by yfinance) finds system CA certs
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# Install Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        "fastapi==0.111.0" \
        "uvicorn[standard]==0.29.0" \
        "sqlalchemy==2.0.30" \
        "alembic==1.13.1" \
        "psycopg2-binary==2.9.9" \
        "pydantic==2.7.1" \
        "pydantic-settings==2.2.1" \
        "passlib[bcrypt]==1.7.4" \
        "bcrypt==3.2.2" \
        "python-jose[cryptography]==3.3.0" \
        "cryptography==42.0.7" \
        "alpaca-py==0.26.0" \
        "apscheduler==3.10.4" \
        "redis==5.0.4" \
        "python-multipart==0.0.9" \
        "httpx==0.27.0" \
        "python-dateutil==2.9.0" \
        "pytz==2024.1" \
        "pyxirr==0.10.8" \
        "yfinance==0.2.50" \
        "curl_cffi>=0.7.0"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
