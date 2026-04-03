#!/bin/bash
# EC2 bootstrap script — run once on a fresh Amazon Linux 2023 / Ubuntu instance.
# After this, use deploy/deploy.sh for subsequent deployments.
set -euo pipefail

echo "=== Installing Docker ==="
if command -v apt-get &>/dev/null; then
    # Ubuntu
    apt-get update -y
    apt-get install -y docker.io docker-compose-v2 nginx git curl
    systemctl enable --now docker
    usermod -aG docker ubuntu
else
    # Amazon Linux 2023
    dnf update -y
    dnf install -y docker nginx git curl
    systemctl enable --now docker
    curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
        -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    usermod -aG docker ec2-user
fi

echo "=== Installing AWS CLI (for ECR pulls) ==="
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
cd /tmp && unzip -q awscliv2.zip && ./aws/install && cd -

echo "=== Configuring Nginx ==="
cp /app/deploy/nginx.conf /etc/nginx/conf.d/nbabetting.conf
# Remove default site if present
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
nginx -t
systemctl enable --now nginx

echo ""
echo "=== EC2 setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Copy your .env file to /app/.env"
echo "  2. cd /app && docker compose -f docker-compose.prod.yml up -d --build"
echo "  3. Run initial data ingestion (see scripts/bootstrap.py)"
echo "  4. Optionally add HTTPS: sudo certbot --nginx -d yourdomain.com"
