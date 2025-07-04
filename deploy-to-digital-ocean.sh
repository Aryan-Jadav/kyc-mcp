#!/bin/bash

# Deploy KYC MCP Server to Digital Ocean
# This script deploys the KYC server to your Digital Ocean droplet

set -e  # Exit on any error

# Configuration
DROPLET_IP="139.59.70.153"
DROPLET_USER="root"
REMOTE_DIR="/opt/kyc-mcp"
LOCAL_DIR="."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we can connect to the server
print_status "Testing connection to Digital Ocean droplet..."
if ! ssh -o ConnectTimeout=10 -o BatchMode=yes $DROPLET_USER@$DROPLET_IP exit 2>/dev/null; then
    print_error "Cannot connect to $DROPLET_IP. Please check:"
    print_error "1. Your SSH key is properly configured"
    print_error "2. The server is running"
    print_error "3. The IP address is correct"
    exit 1
fi
print_success "Connection to droplet successful"

# Create remote directory
print_status "Creating remote directory structure..."
ssh $DROPLET_USER@$DROPLET_IP "mkdir -p $REMOTE_DIR"

# Stop existing containers
print_status "Stopping existing KYC containers..."
ssh $DROPLET_USER@$DROPLET_IP "cd $REMOTE_DIR && docker-compose down 2>/dev/null || true"

# Copy files to server
print_status "Copying files to server..."
rsync -avz --progress \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.env' \
    --exclude='venv' \
    --exclude='node_modules' \
    --exclude='*.log' \
    --exclude='*.db' \
    $LOCAL_DIR/ $DROPLET_USER@$DROPLET_IP:$REMOTE_DIR/

print_success "Files copied successfully"

# Set up environment file
print_status "Setting up environment configuration..."
ssh $DROPLET_USER@$DROPLET_IP "cd $REMOTE_DIR && cp .env.docker .env"

# Build and start the application
print_status "Building Docker image..."
ssh $DROPLET_USER@$DROPLET_IP "cd $REMOTE_DIR && docker-compose build --no-cache"

print_status "Starting KYC MCP Server..."
ssh $DROPLET_USER@$DROPLET_IP "cd $REMOTE_DIR && docker-compose up -d"

# Wait for service to be ready
print_status "Waiting for service to be ready..."
sleep 15

# Check if the service is running
print_status "Checking service health..."
for i in {1..10}; do
    if ssh $DROPLET_USER@$DROPLET_IP "curl -f http://localhost:8000/health > /dev/null 2>&1"; then
        print_success "✅ KYC MCP Server is running and healthy!"
        break
    else
        if [ $i -eq 10 ]; then
            print_error "❌ Service health check failed after 10 attempts"
            print_status "Checking container logs..."
            ssh $DROPLET_USER@$DROPLET_IP "cd $REMOTE_DIR && docker-compose logs --tail=50"
            exit 1
        fi
        print_status "Health check attempt $i/10 failed, retrying in 3 seconds..."
        sleep 3
    fi
done

# Test API endpoints
print_status "Testing API endpoints..."
if ssh $DROPLET_USER@$DROPLET_IP "curl -f http://localhost:8000/docs > /dev/null 2>&1"; then
    print_success "✅ API documentation is accessible"
else
    print_warning "⚠️ API documentation may not be accessible"
fi

# Show final status
print_success "🎉 Deployment completed successfully!"
print_status "Service URLs:"
print_status "  - Health Check: http://$DROPLET_IP:8000/health"
print_status "  - API Documentation: http://$DROPLET_IP:8000/docs"
print_status "  - API Status: http://$DROPLET_IP:8000/api/status"

print_status "To check logs: ssh $DROPLET_USER@$DROPLET_IP 'cd $REMOTE_DIR && docker-compose logs -f'"
print_status "To restart: ssh $DROPLET_USER@$DROPLET_IP 'cd $REMOTE_DIR && docker-compose restart'"
