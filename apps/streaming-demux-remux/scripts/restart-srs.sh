#!/bin/bash

# Restart SRS (Simple Realtime Server) Docker container

CONTAINER_NAME="srs"

echo "🔄 Restarting SRS (Simple Realtime Server)..."

# Check if container exists
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "⏹️  Stopping SRS..."
  docker stop ${CONTAINER_NAME} 2>/dev/null
  
  sleep 1
  
  echo "▶️  Starting SRS..."
  docker start ${CONTAINER_NAME}
  
  sleep 2
  
  # Verify it's running
  if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo ""
    echo "✅ SRS restarted successfully!"
    echo ""
    echo "📊 Container Status:"
    docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    echo ""
    echo "🌐 SRS Web UI: http://localhost:8080"
    echo "📡 RTMP Port: 1935"
    echo "🔧 API Port: 1985"
  else
    echo ""
    echo "❌ Failed to restart SRS"
    exit 1
  fi
else
  echo "ℹ️  SRS container does not exist. Creating new container..."
  bash "$(dirname "$0")/start-srs.sh"
fi

