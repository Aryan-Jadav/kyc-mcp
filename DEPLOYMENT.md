# KYC MCP Server - Digital Ocean Deployment Guide

## Prerequisites

1. **Digital Ocean Droplet** with Docker installed
2. **SSH access** to your droplet as root
3. **Your droplet's IP address**

## Quick Deployment (Automated)

### Option 1: Using Upload Script (Windows)

1. **Update the script** with your droplet IP:
   ```cmd
   notepad upload_to_digitalocean.bat
   ```
   Change `YOUR_DROPLET_IP` to your actual IP address.

2. **Run the deployment**:
   ```cmd
   upload_to_digitalocean.bat
   ```

### Option 2: Manual Deployment

1. **Create archive locally**:
   ```cmd
   tar -czf kyc-mcp-server.tar.gz --exclude=venv --exclude=__pycache__ --exclude=*.db --exclude=*.log --exclude=.git *.py *.txt *.yml *.sh .env* .dockerignore Dockerfile README.md TROUBLESHOOTING.md
   ```

2. **Upload to server**:
   ```cmd
   scp kyc-mcp-server.tar.gz root@YOUR_DROPLET_IP:/root/
   ```

3. **SSH to server and deploy**:
   ```cmd
   ssh root@YOUR_DROPLET_IP
   ```

   Then on the server:
   ```bash
   # Extract files
   mkdir -p /root/kyc-mcp-server
   cd /root/kyc-mcp-server
   tar -xzf /root/kyc-mcp-server.tar.gz
   rm /root/kyc-mcp-server.tar.gz

   # Setup environment
   cp .env.docker .env

   # Deploy
   chmod +x deploy.sh
   ./deploy.sh
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
