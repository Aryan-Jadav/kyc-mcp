#!/bin/bash

# KYC MCP Server Deployment Script for Digital Ocean
# Run this script on your Digital Ocean droplet

set -e  # Exit on any error

echo "🚀 Starting KYC MCP Server deployment..."

# Configuration
PROJECT_NAME="kyc-mcp-server"
CONTAINER_NAME="kyc-mcp-server"
PORT=8000

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

# Determine Docker Compose command
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
elif docker compose version &> /dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
else
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

print_status "Using Docker Compose command: $DOCKER_COMPOSE"

# Stop existing containers
print_status "Stopping existing containers..."
$DOCKER_COMPOSE down 2>/dev/null || true

# Remove old images (optional)
print_status "Cleaning up old images..."
docker image prune -f

# Copy environment file
print_status "Setting up environment..."
if [ -f ".env.docker" ]; then
    cp .env.docker .env
    print_status "Environment file configured"
else
    print_warning "No .env.docker file found, using defaults"
fi

# Build the new image
print_status "Building Docker image..."
if $DOCKER_COMPOSE build --no-cache; then
    print_status "✅ Docker image built successfully"
else
    print_error "❌ Failed to build Docker image"
    exit 1
fi

# Start the services
print_status "Starting services..."
if $DOCKER_COMPOSE up -d; then
    print_status "✅ Services started successfully"
else
    print_error "❌ Failed to start services"
    exit 1
fi

# Wait for services to be ready
print_status "Waiting for services to be ready..."
sleep 15

# Check if the service is running
print_status "Checking service health..."
for i in {1..5}; do
    if curl -f http://localhost:$PORT/health > /dev/null 2>&1; then
        print_status "✅ KYC MCP Server is running and healthy"
        break
    else
        print_warning "⚠️  Attempt $i: Service not ready yet, waiting..."
        sleep 5
    fi
done

# Show status
print_status "Deployment completed! 🎉"
echo ""
echo "📊 Service Status:"
$DOCKER_COMPOSE ps

echo ""
echo "🔗 Service URLs:"
echo "   Health Check: http://localhost:$PORT/health"
echo "   API Documentation: http://localhost:$PORT/docs"
echo "   API Status: http://localhost:$PORT/api/status"

echo ""
echo "📝 Useful Commands:"
echo "   View logs: $DOCKER_COMPOSE logs -f"
echo "   Stop services: $DOCKER_COMPOSE down"
echo "   Restart services: $DOCKER_COMPOSE restart"
echo "   Update and redeploy: ./deploy.sh"

echo ""
echo "🔥 Opening firewall port $PORT..."
if command -v ufw &> /dev/null; then
    ufw allow $PORT 2>/dev/null || print_warning "Could not configure firewall automatically"
fi

echo ""
print_status "Deployment completed successfully! ✨"
