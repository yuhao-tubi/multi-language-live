#!/bin/bash

# Stop SRS (Simple Realtime Server) Docker container

CONTAINER_NAME="srs"

echo "🛑 Stopping SRS (Simple Realtime Server)..."

# Check if container exists
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  # Check if it's running
  if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "⏹️  Stopping SRS container..."
    docker stop ${CONTAINER_NAME}
    echo "✅ SRS stopped successfully"
  else
    echo "ℹ️  SRS container exists but is not running"
  fi
  
  # Ask if user wants to remove the container
  echo ""
  echo "💡 Container is stopped but still exists."
  echo "   To remove it completely, run: docker rm ${CONTAINER_NAME}"
  echo "   Or use: npm run srs:remove"
else
  echo "ℹ️  SRS container does not exist"
fi

