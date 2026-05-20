# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for PostgreSQL and frontend build
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy source code
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

# Build frontend
WORKDIR /app/frontend
RUN npm install
RUN npm run build

# Move to Django backend
WORKDIR /app/backend

# Collect static files
# SECRET_KEY はビルド時のダミー値。実行時は Render の環境変数で上書きされる。
RUN SECRET_KEY=build-time-dummy-not-used-at-runtime \
    python manage.py collectstatic --noinput

# Expose port
EXPOSE 8000

# Start: マイグレーション適用 → gunicorn 起動
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000"]