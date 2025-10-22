#!/bin/bash

# View SRS (Simple Realtime Server) logs

CONTAINER_NAME="srs"

echo "📋 Viewing SRS logs (press Ctrl+C to exit)..."
echo ""

# Check if container exists
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  docker logs -f ${CONTAINER_NAME}
else
  echo "❌ SRS container does not exist"
  echo "💡 Start SRS first: npm run srs:start"
  exit 1
fi

