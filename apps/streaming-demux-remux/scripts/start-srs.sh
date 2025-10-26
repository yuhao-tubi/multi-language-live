#!/bin/bash

# Start SRS (Simple Realtime Server) in Docker
# This script checks if SRS is already running and starts it if not

CONTAINER_NAME="srs"
IMAGE="ossrs/srs:5"

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# Config file is in the parent directory of the scripts folder
CONFIG_PATH="${SCRIPT_DIR}/../srt.conf"

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
    echo "🔌 SRT Port: 10080/udp"
    echo "🔧 API Port: 1985"
    exit 0
  else
    echo "▶️  Starting existing SRS container..."
    docker start ${CONTAINER_NAME}
  fi
else
  echo "📦 Creating new SRS container with SRT support..."
  echo "📄 Using config: ${CONFIG_PATH}"
  docker run -d \
    -p 1935:1935 \
    -p 1985:1985 \
    -p 8080:8080 \
    -p 10080:10080/udp \
    -v "${CONFIG_PATH}:/usr/local/srs/conf/srt.conf:ro" \
    --name ${CONTAINER_NAME} \
    ${IMAGE} \
    ./objs/srs -c conf/srt.conf
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
  echo "📡 RTMP Port: 1935"
  echo "🔌 SRT Port: 10080/udp (srt://localhost:10080)"
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

