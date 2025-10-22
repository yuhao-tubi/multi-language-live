#!/bin/bash

# Start SRS (Simple Realtime Server) in Docker
# This script checks if SRS is already running and starts it if not

CONTAINER_NAME="srs"
IMAGE="ossrs/srs:5"

echo "🚀 Starting SRS (Simple Realtime Server)..."

# Check if container exists and is running
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "✅ SRS is already running"
    echo ""
    echo "📊 SRS Status:"
    docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    echo ""
    echo "🌐 SRS Web UI: http://localhost:8080"
    echo "📡 RTMP Port: 1935"
    echo "🔧 API Port: 1985"
    exit 0
  else
    echo "▶️  Starting existing SRS container..."
    docker start ${CONTAINER_NAME}
  fi
else
  echo "📦 Creating new SRS container..."
  docker run -d \
    -p 1935:1935 \
    -p 1985:1985 \
    -p 8080:8080 \
    --name ${CONTAINER_NAME} \
    ${IMAGE}
fi

# Wait a moment for startup
sleep 2

# Verify it's running
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo ""
  echo "✅ SRS started successfully!"
  echo ""
  echo "📊 Container Status:"
  docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
  echo ""
  echo "🌐 SRS Web UI: http://localhost:8080"
  echo "📡 RTMP Port: 1935 (rtmp://localhost/live/stream)"
  echo "🔧 API Port: 1985"
  echo ""
  echo "📝 View logs: docker logs -f ${CONTAINER_NAME}"
  echo "🛑 Stop SRS: npm run srs:stop"
else
  echo ""
  echo "❌ Failed to start SRS"
  echo "📋 Check logs: docker logs ${CONTAINER_NAME}"
  exit 1
fi

