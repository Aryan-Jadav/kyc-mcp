#!/bin/bash

# KYC MCP Server Deployment Script for Digital Ocean
# Run this script on your Digital Ocean droplet

set -e  # Exit on any error

echo "🚀 Starting KYC MCP Server deployment..."

# Configuration
PROJECT_NAME="kyc-mcp-server"
CONTAINER_NAME="kyc-mcp-server"
IMAGE_NAME="kyc-mcp:latest"
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

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Stop existing containers
print_status "Stopping existing containers..."
docker-compose down 2>/dev/null || docker compose down 2>/dev/null || true

# Remove old images (optional)
print_status "Cleaning up old images..."
docker image prune -f

# Build the new image
print_status "Building Docker image..."
if docker-compose build || docker compose build; then
    print_status "✅ Docker image built successfully"
else
    print_error "❌ Failed to build Docker image"
    exit 1
fi

# Start the services
print_status "Starting services..."
if docker-compose up -d || docker compose up -d; then
    print_status "✅ Services started successfully"
else
    print_error "❌ Failed to start services"
    exit 1
fi

# Wait for services to be ready
print_status "Waiting for services to be ready..."
sleep 10

# Check if the service is running
if curl -f http://localhost:$PORT/health > /dev/null 2>&1; then
    print_status "✅ KYC MCP Server is running and healthy"
else
    print_warning "⚠️  Service might still be starting up. Check logs with: docker-compose logs -f"
fi

# Show status
print_status "Deployment completed! 🎉"
echo ""
echo "📊 Service Status:"
docker-compose ps || docker compose ps

echo ""
echo "🔗 Service URLs:"
echo "   Health Check: http://localhost:$PORT/health"
echo "   API Documentation: http://localhost:$PORT/docs"
echo "   API Status: http://localhost:$PORT/api/status"

echo ""
echo "📝 Useful Commands:"
echo "   View logs: docker-compose logs -f"
echo "   Stop services: docker-compose down"
echo "   Restart services: docker-compose restart"
echo "   Update and redeploy: ./deploy.sh"

echo ""
print_status "Deployment completed successfully! ✨"
