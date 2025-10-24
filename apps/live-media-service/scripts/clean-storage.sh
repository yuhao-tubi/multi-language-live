#!/bin/bash

# Clean storage directories

STORAGE_DIR="./storage"

echo "🧹 Cleaning storage directories..."

if [ -d "$STORAGE_DIR" ]; then
    rm -rf "$STORAGE_DIR"
    echo "✅ Storage cleaned"
else
    echo "ℹ️  Storage directory doesn't exist"
fi

# Recreate empty structure
mkdir -p "$STORAGE_DIR"/{original_stream,processed_fragments/{video,audio,processed_audio,output},logs}

echo "✅ Storage structure recreated"

