# KYC MCP Server - Digital Ocean Deployment Guide

## Prerequisites

1. **Digital Ocean Droplet** with Docker installed
2. **SSH access** to your droplet as root
3. **Git repository** with your KYC MCP code

## Quick Deployment from Git (Recommended)

### Step 1: SSH to Your Digital Ocean Server
```bash
ssh root@YOUR_DROPLET_IP
```

### Step 2: Clone Repository
```bash
# Navigate to deployment directory
cd /opt/mcp

# Clone your repository (replace with your actual Git URL)
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git kyc-mcp-server

# Navigate to project directory
cd kyc-mcp-server
```

### Step 3: Deploy
```bash
# Make deploy script executable
chmod +x deploy.sh

# Run deployment
./deploy.sh
```

That's it! The deployment script will:
- Set up environment variables
- Build Docker image
- Start the service
- Configure firewall
- Verify health

## Alternative: Manual Git Deployment

If the automated script has issues:

```bash
# Clone repository
cd /opt/mcp
git clone YOUR_GIT_REPO_URL kyc-mcp-server
cd kyc-mcp-server

# Setup environment
cp .env.docker .env

# Build and start
docker compose build --no-cache
docker compose up -d

# Check status
docker compose ps
curl http://localhost:8000/health

# Open firewall
ufw allow 8000
```

## Verification

After deployment, verify the service is running:

```bash
# Check service status
docker-compose ps

# Check health
curl http://localhost:8000/health

# Check API status
curl http://localhost:8000/api/status

# View logs
docker-compose logs -f
```

## Service URLs

Once deployed, your service will be available at:

- **Health Check**: `http://YOUR_DROPLET_IP:8000/health`
- **API Documentation**: `http://YOUR_DROPLET_IP:8000/docs`
- **API Status**: `http://YOUR_DROPLET_IP:8000/api/status`

## Management Commands

```bash
# View logs
docker-compose logs -f

# Restart service
docker-compose restart

# Stop service
docker-compose down

# Update and redeploy
./deploy.sh

# Check resource usage
docker stats

# Access container shell
docker-compose exec kyc-server bash
```

## Firewall Configuration

Make sure port 8000 is open on your droplet:

```bash
# Using ufw (Ubuntu)
ufw allow 8000

# Using iptables
iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
```

## SSL/HTTPS Setup (Optional)

For production, consider setting up SSL with nginx:

```bash
# Install nginx
apt update && apt install nginx

# Install certbot for Let's Encrypt
apt install certbot python3-certbot-nginx

# Configure nginx proxy (create /etc/nginx/sites-available/kyc-mcp)
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

# Enable site and get SSL certificate
ln -s /etc/nginx/sites-available/kyc-mcp /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d your-domain.com
```

## Troubleshooting

### Service won't start
```bash
# Check logs
docker-compose logs kyc-server

# Check if port is in use
netstat -tulpn | grep 8000

# Rebuild and restart
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### API token issues
```bash
# Check environment variables
docker-compose exec kyc-server env | grep SUREPASS

# Update token
nano .env
docker-compose restart
```

### Database issues
```bash
# Check database file permissions
docker-compose exec kyc-server ls -la /app/data/

# Reset database
docker-compose down
docker volume rm kyc-mcp-server_kyc_data
docker-compose up -d
```

## Monitoring

Set up basic monitoring:

```bash
# Create monitoring script
cat > /root/monitor_kyc.sh << 'EOF'
#!/bin/bash
if ! curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "KYC service is down, restarting..."
    cd /root/kyc-mcp-server && docker-compose restart
fi
EOF

chmod +x /root/monitor_kyc.sh

# Add to crontab (check every 5 minutes)
echo "*/5 * * * * /root/monitor_kyc.sh" | crontab -
```

## Backup

Regular backup of data:

```bash
# Create backup script
cat > /root/backup_kyc.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/root/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR
docker-compose exec kyc-server tar -czf - /app/data | cat > $BACKUP_DIR/kyc_data_$DATE.tar.gz

# Keep only last 7 backups
ls -t $BACKUP_DIR/kyc_data_*.tar.gz | tail -n +8 | xargs rm -f
EOF

chmod +x /root/backup_kyc.sh

# Add to crontab (daily backup at 2 AM)
echo "0 2 * * * /root/backup_kyc.sh" | crontab -
```
