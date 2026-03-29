#!/bin/bash
set -e

# ── Install Docker ─────────────────────────────────────────────────────────────
dnf install -y docker git
systemctl enable --now docker
usermod -aG docker ec2-user

# ── Install Docker Compose plugin ─────────────────────────────────────────────
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# ── Install AWS CLI v2 ─────────────────────────────────────────────────────────
curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
dnf install -y unzip
unzip -q /tmp/awscliv2.zip -d /tmp
/tmp/aws/install

# ── Install Nginx ──────────────────────────────────────────────────────────────
dnf install -y nginx
systemctl enable nginx

# ── App directory ──────────────────────────────────────────────────────────────
mkdir -p /app
chown ec2-user:ec2-user /app

# ── Write .env for docker-compose ─────────────────────────────────────────────
cat > /app/.env <<EOF
ECR_REGISTRY=${ecr_registry}
AWS_REGION=${aws_region}
APP_NAME=${app_name}
ANTHROPIC_API_KEY=${anthropic_api_key}
FINMIND_TOKEN=${finmind_token}
DB_PATH=/data/ledger.db
TZ=Asia/Taipei
AUTO_REFRESH_QUOTES_ON_TRADE=1
QUOTE_PROVIDER=auto
MCP_TRANSPORT=streamable-http
FASTMCP_HOST=0.0.0.0
FASTMCP_PORT=8001
EOF
chmod 600 /app/.env

# ── Nginx reverse proxy config ─────────────────────────────────────────────────
cat > /etc/nginx/conf.d/${app_name}.conf <<'NGINX'
server {
    listen 80;
    server_name _;

    # Gzip compression
    gzip            on;
    gzip_vary       on;
    gzip_proxied    any;
    gzip_comp_level 5;
    gzip_types      text/plain text/css application/json application/javascript
                    text/xml application/xml application/xml+rss text/javascript
                    image/svg+xml;

    # Increase timeouts for SSE streaming (JARVIS)
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;

    # API → FastAPI
    location /api/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        # Disable buffering for SSE streaming
        proxy_buffering    off;
        proxy_cache        off;
    }

    # Next.js static assets — long-lived cache (content-hashed filenames)
    location /_next/static/ {
        proxy_pass         http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        add_header         Cache-Control "public, max-age=31536000, immutable";
    }

    # Web → Next.js
    location / {
        proxy_pass         http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
    }
}
NGINX

systemctl restart nginx
