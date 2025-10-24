#!/bin/bash

# Start SRS (Simple Realtime Server) in Docker
# This script starts SRS for RTMP ingestion and HLS output

CONTAINER_NAME="srs-live-media"
SRS_VERSION="5"
RTMP_PORT=1935
HTTP_PORT=8080
API_PORT=1985

echo "🚀 Starting SRS (Simple Realtime Server)..."

# Check if container already exists
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Container ${CONTAINER_NAME} already exists"
    
    # Check if it's running
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "✅ SRS is already running"
        exit 0
    else
        echo "Starting existing container..."
        docker start ${CONTAINER_NAME}
        echo "✅ SRS started successfully"
        exit 0
    fi
fi

# Start new container
echo "Creating new SRS container..."
docker run -d \
    --name ${CONTAINER_NAME} \
    -p ${RTMP_PORT}:1935 \
    -p ${HTTP_PORT}:8080 \
    -p ${API_PORT}:1985 \
    --restart unless-stopped \
    ossrs/srs:${SRS_VERSION}

if [ $? -eq 0 ]; then
    echo "✅ SRS started successfully"
    echo ""
    echo "📡 SRS Endpoints:"
    echo "  RTMP: rtmp://localhost:${RTMP_PORT}/live"
    echo "  HLS:  http://localhost:${HTTP_PORT}/live"
    echo "  API:  http://localhost:${API_PORT}/api/v1"
    echo ""
    echo "📝 To publish a stream:"
    echo "  ffmpeg -re -i input.mp4 -c copy -f flv rtmp://localhost:${RTMP_PORT}/live/stream"
    echo ""
    echo "📺 To play HLS stream:"
    echo "  http://localhost:${HTTP_PORT}/live/stream.m3u8"
else
    echo "❌ Failed to start SRS"
    exit 1
fi

