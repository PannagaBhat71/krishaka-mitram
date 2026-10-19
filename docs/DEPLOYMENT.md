# Deployment Guide

## Overview

This guide covers production deployment of Krishaka Mitram on Linux servers (bare metal, VM, or cloud) and Render.com. The application uses Django with Channels (ASGI), requiring Daphne for WebSocket support and Redis for the channel layer.

## Prerequisites (Production Server)

- **OS**: Ubuntu 22.04+ / Debian 12+ / RHEL 9+
- **Python**: 3.12+
- **PostgreSQL**: 14+
- **Redis**: 7+
- **Nginx**: 1.24+
- **Systemd**: For service management

## Option 1: Render.com (Recommended for Simplicity)

### 1. Repository Setup
```bash
# Ensure these files are committed:
# - render.yaml
# - build.sh
# - requirements.txt
# - kisan/settings.py (production-ready)
```

### 2. Render Dashboard Configuration

1. **Create New Web Service** → Connect GitHub/GitLab repo
2. **Settings**:
   - **Runtime**: Python 3.12
   - **Build Command**: `./build.sh`
   - **Start Command**: `daphne -b 0.0.0.0 -p $PORT kisan.asgi:application`
3. **Environment Variables**:
   - `PYTHON_VERSION` = `3.12.0`
   - `DEBUG` = `False`
   - `SECRET_KEY` = *Generate* (Render provides "Generate Value")
   - `ALLOWED_HOSTS` = `*` (or your custom domain)
   - `REDIS_URL` = *Link to Redis add-on*
4. **Add Redis Add-on**:
   - Create Redis instance in Render
   - Link `REDIS_URL` environment variable to the Redis add-on
5. **Custom Domain** (optional):
   - Add domain in Render settings
   - Render automatically sets `RENDER_EXTERNAL_HOSTNAME` → adds to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`

### 3. Deploy
- Push to main branch → auto-deploys
- Check logs for `build.sh` output and Daphne startup

---

## Option 2: Manual Linux Deployment

### 1. Server Preparation

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3.12 python3.12-venv python3.12-dev \
    postgresql postgresql-contrib redis-server nginx \
    git build-essential libpq-dev

# Verify versions
python3.12 --version  # 3.12.x
psql --version        # 14+
redis-server --version # 7+
nginx -v              # 1.24+
```

### 2. PostgreSQL Setup

```bash
# Create database and user
sudo -u postgres psql << 'EOF'
CREATE DATABASE krishaka_mitram;
CREATE USER krishaka WITH ENCRYPTED PASSWORD 'strong-random-password';
GRANT ALL PRIVILEGES ON DATABASE krishaka_mitram TO krishaka;
ALTER USER krishaka CREATEDB;  -- Needed for test database creation
\q
EOF

# Test connection
psql -U krishaka -h localhost -d krishaka_mitram -c "SELECT version();"
```

### 3. Redis Configuration

```bash
# Configure Redis for production
sudo sed -i 's/^bind 127.0.0.1/bind 127.0.0.1 ::1/' /etc/redis/redis.conf
sudo sed -i 's/^# maxmemory <bytes>/maxmemory 256mb/' /etc/redis/redis.conf
sudo sed -i 's/^# maxmemory-policy noeviction/maxmemory-policy allkeys-lru/' /etc/redis/redis.conf

# Enable and start
sudo systemctl enable --now redis-server

# Test
redis-cli ping  # PONG
```

### 4. Application Deployment

```bash
# Create deployment user
sudo useradd -r -m -s /bin/bash -d /opt/krishaka-mitram krishaka

# Clone repository
sudo -u krishaka git clone <your-repo-url> /opt/krishaka-mitram
cd /opt/krishaka-mitram

# Create virtual environment
sudo -u krishaka python3.12 -m venv venv
sudo -u krishaka /opt/krishaka-mitram/venv/bin/pip install --upgrade pip
sudo -u krishaka /opt/krishaka-mitram/venv/bin/pip install -r requirements.txt

# Create environment file
sudo -u krishaka cat > /opt/krishaka-mitram/.env << 'EOF'
DEBUG=False
SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_urlsafe(50))">
DATABASE_URL=postgres://krishaka:strong-random-password@localhost:5432/krishaka_mitram
REDIS_URL=redis://localhost:6379/0
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
VIOLATION_AUTO_PURGE_DAYS=30
# Email settings (configure for production)
# EMAIL_HOST=smtp.yourprovider.com
# EMAIL_PORT=587
# EMAIL_HOST_USER=your-email
# EMAIL_HOST_PASSWORD=your-password
# EMAIL_USE_TLS=True
EOF

# Secure permissions
sudo chmod 600 /opt/krishaka-mitram/.env
sudo chown krishaka:krishaka /opt/krishaka-mitram/.env
```

### 5. Django Setup

```bash
cd /opt/krishaka-mitram
sudo -u krishaka /opt/krishaka-mitram/venv/bin/python manage.py migrate
sudo -u krishaka /opt/krishaka-mitram/venv/bin/python manage.py collectstatic --no-input
sudo -u krishaka /opt/krishaka-mitram/venv/bin/python manage.py load_agri_data

# Create superuser
sudo -u krishaka /opt/krishaka-mitram/venv/bin/python manage.py createsuperuser
```

### 6. Systemd Service (Daphne ASGI)

```bash
sudo cat > /etc/systemd/system/krishaka-mitram.service << 'EOF'
[Unit]
Description=Krishaka Mitram Daphne ASGI Server
Documentation=https://github.com/yourorg/krishaka-mitram
After=network.target redis-server.service postgresql.service
Wants=redis-server.service postgresql.service

[Service]
Type=simple
User=krishaka
Group=krishaka
WorkingDirectory=/opt/krishaka-mitram
EnvironmentFile=/opt/krishaka-mitram/.env
# Use multiple workers for production (adjust based on CPU cores)
ExecStart=/opt/krishaka-mitram/venv/bin/daphne \
    -b 127.0.0.1 \
    -p 8000 \
    --proxy-headers \
    --access-log - \
    --verbosity 1 \
    kisan.asgi:application
Restart=on-failure
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=3

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/krishaka-mitram
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable --now krishaka-mitram
sudo systemctl status krishaka-mitram
```

### 7. Nginx Reverse Proxy with WebSocket Support

```bash
sudo cat > /etc/nginx/sites-available/krishaka-mitram << 'EOF'
# Upstream for Daphne (can add multiple for scaling)
upstream krishaka_backend {
    server 127.0.0.1:8000;
    # server 127.0.0.1:8001;  # Add more workers here
    keepalive 32;
}

server {
    listen 80;
    listen [::]:80;
    server_name yourdomain.com www.yourdomain.com;

    # Redirect HTTP to HTTPS (after SSL cert configured)
    # return 301 https://$server_name$request_uri;

    # Temporary: serve directly for testing
    root /opt/krishaka-mitram/staticfiles;

    # Static files (served directly by Nginx)
    location /static/ {
        alias /opt/krishaka-mitram/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
        try_files $uri =404;
    }

    # Media files (if configured)
    # location /media/ {
    #     alias /opt/krishaka-mitram/media/;
    #     expires 30d;
    # }

    # Proxy to Daphne
    location / {
        proxy_pass http://krishaka_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        
        # WebSocket timeouts
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
        
        # Buffer settings
        proxy_buffering off;
        proxy_cache off;
        
        # Health check endpoint
        # access_log /var/log/nginx/krishaka_access.log;
        # error_log /var/log/nginx/krishaka_error.log;
    }

    # Health check (no auth, no logging)
    location /health/ {
        proxy_pass http://krishaka_backend;
        access_log off;
        proxy_set_header Host $host;
    }

    # Security headers
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}
EOF

# Enable site
sudo ln -sf /etc/nginx/sites-available/krishaka-mitram /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test and reload
sudo nginx -t
sudo systemctl reload nginx
```

### 8. SSL/TLS with Let's Encrypt (Certbot)

```bash
# Install certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtain certificate (run after DNS is configured)
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Auto-renewal is configured by certbot via systemd timer
sudo systemctl status certbot.timer
```

### 9. Firewall

```bash
# UFW (Ubuntu)
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable

# Verify
sudo ufw status
```

---

## Docker Deployment (Alternative)

### Dockerfile

```dockerfile
# Dockerfile
FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -r -m -s /bin/bash -d /app appuser

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application
COPY --chown=appuser:appuser . .

# Collect static files (requires env vars)
ARG SECRET_KEY=build-time-key
ARG DEBUG=False
ARG DATABASE_URL=postgres://user:pass@db:5432/db
ARG REDIS_URL=redis://redis:6379/0
ENV SECRET_KEY=$SECRET_KEY \
    DEBUG=$DEBUG \
    DATABASE_URL=$DATABASE_URL \
    REDIS_URL=$REDIS_URL

RUN python manage.py collectstatic --no-input

USER appuser

EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "kisan.asgi:application"]
```

### docker-compose.yml

```yaml
# docker-compose.yml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DEBUG=False
      - SECRET_KEY=${SECRET_KEY}
      - DATABASE_URL=postgres://krishaka:${POSTGRES_PASSWORD}@db:5432/krishaka_mitram
      - REDIS_URL=redis://redis:6379/0
      - ALLOWED_HOSTS=${ALLOWED_HOSTS}
      - VIOLATION_AUTO_PURGE_DAYS=30
    depends_on:
      - db
      - redis
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 512M

  db:
    image: postgres:16-alpine
    environment:
      - POSTGRES_DB=krishaka_mitram
      - POSTGRES_USER=krishaka
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U krishaka"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certbot/conf:/etc/letsencrypt:ro
      - ./certbot/www:/var/www/certbot:ro
    depends_on:
      - web
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

### nginx.conf (for Docker)

```nginx
# nginx.conf
events {
    worker_connections 1024;
}

http {
    upstream krishaka_backend {
        server web:8000;
        keepalive 32;
    }

    server {
        listen 80;
        server_name yourdomain.com www.yourdomain.com;

        location /static/ {
            alias /app/staticfiles/;
            expires 1y;
            add_header Cache-Control "public, immutable";
        }

        location / {
            proxy_pass http://krishaka_backend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 86400;
            proxy_send_timeout 86400;
            proxy_buffering off;
        }

        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }
    }
}
```

### Deploy with Docker Compose

```bash
# Create .env file
cat > .env << 'EOF'
SECRET_KEY=your-generated-secret-key
POSTGRES_PASSWORD=strong-db-password
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
EOF

# Build and start
docker compose up -d --build

# Run migrations
docker compose exec web python manage.py migrate
docker compose exec web python manage.py load_agri_data
docker compose exec web python manage.py createsuperuser

# View logs
docker compose logs -f web
```

---

## Health Checks & Monitoring

### Health Check Endpoint

Add to `kisan/urls.py`:
```python
from django.http import JsonResponse
from django.db import connection

def health_check(request):
    # Check database
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_status = "ok"
    except Exception:
        db_status = "error"
    
    return JsonResponse({
        "status": "healthy" if db_status == "ok" else "unhealthy",
        "database": db_status,
        "version": "1.0.0"
    })
```

### Monitoring Checklist

- [ ] **Uptime**: Ping `/health/` every 30s
- [ ] **Daphne workers**: Check process count matches CPU cores
- [ ] **Redis memory**: Alert if > 80% maxmemory
- [ ] **PostgreSQL connections**: Alert if > 80% max_connections
- [ ] **Disk space**: Alert if > 80% on `/opt/krishaka-mitram` and `/var/lib/postgresql`
- [ ] **Error rate**: Monitor 5xx responses in Nginx logs
- [ ] **WebSocket connections**: Track active connections via Redis `INFO clients`

---

## Backup & Restore

### Automated Daily Backup (Cron)

```bash
# /etc/cron.d/krishaka-backup
# Run at 2:30 AM daily
30 2 * * * krishaka /opt/krishaka-mitram/venv/bin/python /opt/krishaka-mitram/manage.py dumpdata --exclude=contenttypes --exclude=auth.permission --exclude=sessions > /opt/krishaka-mitram/backups/fixtures_$(date +\%F).json 2>/dev/null

# PostgreSQL backup
30 2 * * * postgres pg_dump -U krishaka -h localhost krishaka_mitram | gzip > /opt/krishaka-mitram/backups/db_$(date +\%F).sql.gz

# Cleanup old backups (keep 30 days)
0 3 * * * root find /opt/krishaka-mitram/backups -name "*.json" -mtime +30 -delete
0 3 * * * root find /opt/krishaka-mitram/backups -name "*.sql.gz" -mtime +30 -delete
```

### Restore Procedure

```bash
# 1. Stop application
sudo systemctl stop krishaka-mitram

# 2. Restore database
gunzip -c /opt/krishaka-mitram/backups/db_2026-10-19.sql.gz | sudo -u postgres psql krishaka_mitram

# 3. Restore media/static if needed
# (staticfiles are regenerated by collectstatic)

# 4. Start application
sudo systemctl start krishaka-mitram
```

---

## Rollback Strategy

### Code Rollback
```bash
# On server
cd /opt/krishaka-mitram
sudo -u krishaka git log --oneline -10  # Find commit to rollback to
sudo -u krishaka git checkout <commit-hash>
sudo -u krishaka /opt/krishaka-mitram/venv/bin/pip install -r requirements.txt
sudo -u krishaka /opt/krishaka-mitram/venv/bin/python manage.py migrate
sudo -u krishaka /opt/krishaka-mitram/venv/bin/python manage.py collectstatic --no-input
sudo systemctl restart krishaka-mitram
```

### Database Rollback (if migration caused issues)
```bash
# 1. Identify last good migration
python manage.py showmigrations

# 2. Fake rollback (if migration was applied but schema is compatible)
python manage.py migrate <app> <migration-name> --fake

# 3. Or restore from backup (see Backup & Restore)
```

---

## Scaling Guide

### Horizontal Scaling (Multiple Daphne Workers)

1. **Systemd**: Create multiple service files (`krishaka-mitram@1.service`, `krishaka-mitram@2.service`) with different ports
2. **Nginx**: Add multiple `server` entries in `upstream` block
3. **Redis**: Single Redis instance handles channel layer for all workers

### Database Read Replicas

```python
# kisan/settings.py addition
DATABASES = {
    'default': dj_database_url.parse(os.environ.get('DATABASE_URL')),
    'replica': dj_database_url.parse(os.environ.get('DATABASE_REPLICA_URL')),
}

# Use in views
Farmer.objects.using('replica').filter(...)
```

### CDN for Static Files

Configure `STATIC_URL = 'https://cdn.yourdomain.com/static/'` and upload `staticfiles/` to CDN (Cloudflare, AWS CloudFront, etc.)

---

## Deployment Checklist

### Pre-Deployment
- [ ] All tests pass (`python manage.py test --settings=kisan.test_settings`)
- [ ] `python manage.py check --deploy` passes (with production SECRET_KEY)
- [ ] `python manage.py makemigrations --check --dry-run` shows no pending migrations
- [ ] Environment variables configured (SECRET_KEY, DATABASE_URL, REDIS_URL, ALLOWED_HOSTS)
- [ ] SSL certificate obtained (Let's Encrypt or paid)
- [ ] Redis configured with persistence (AOF/RDB) and memory limits
- [ ] PostgreSQL tuned (shared_buffers, work_mem, max_connections)

### Post-Deployment Verification
- [ ] HTTP site loads (`https://yourdomain.com/`)
- [ ] WebSocket connects (`wss://yourdomain.com/ws/chat/1/`)
- [ ] Admin panel accessible (`/admin/`)
- [ ] Static files served with correct headers (Cache-Control, gzip)
- [ ] Chat sends/receives messages in real-time
- [ ] Moderation dashboard loads for moderator users
- [ ] Notifications appear in real-time
- [ ] Language toggle works (EN/KN)
- [ ] Cookie consent banner appears
- [ ] Health check endpoint returns 200

### Ongoing Maintenance
- [ ] Weekly: Check disk space, log rotation
- [ ] Monthly: Update dependencies (security patches), review audit logs
- [ ] Quarterly: Rotate SECRET_KEY, review user restrictions, test backup restore
- [ ] On security advisories: Update Django, channels, redis, cryptography immediately

---

## Environment-Specific Notes

### Development (Local)
- `DEBUG=true`
- SQLite database (`db.sqlite3`)
- Redis on port 6380 (Docker: `-p 6380:6379`)
- InMemoryChannelLayer (no Redis required if DEBUG=True)
- `python manage.py runserver` + separate `daphne` process

### Staging
- Mirrors production but with staging domain
- `DEBUG=False` (test production behavior)
- Separate PostgreSQL database
- Separate Redis instance
- Reduced resources

### Production
- `DEBUG=False`
- PostgreSQL with connection pooling (PgBouncer recommended)
- Redis with AOF persistence
- Multiple Daphne workers behind Nginx
- CDN for static assets
- Monitoring + alerting configured
- Automated backups verified