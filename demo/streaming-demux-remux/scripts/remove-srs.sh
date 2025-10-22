#!/bin/bash

# Remove SRS (Simple Realtime Server) Docker container completely

CONTAINER_NAME="srs"

echo "🗑️  Removing SRS (Simple Realtime Server) container..."

# Check if container exists
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  # Stop if running
  if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "⏹️  Stopping SRS..."
    docker stop ${CONTAINER_NAME}
  fi
  
  echo "🗑️  Removing container..."
  docker rm ${CONTAINER_NAME}
  echo "✅ SRS container removed successfully"
  echo ""
  echo "💡 To start SRS again, run: npm run srs:start"
else
  echo "ℹ️  SRS container does not exist"
fi

