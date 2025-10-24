#!/bin/bash

# Stop SRS container

CONTAINER_NAME="srs-live-media"

echo "🛑 Stopping SRS..."

if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    docker stop ${CONTAINER_NAME}
    echo "✅ SRS stopped"
else
    echo "ℹ️  SRS is not running"
fi

