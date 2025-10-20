#!/bin/bash

# Setup Verification Script
# Checks if all required dependencies are properly installed

set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║          Setup Verification for HLS Audio Pipeline         ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

ERRORS=0

# Check Node.js
echo "🔍 Checking Node.js..."
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    echo "✅ Node.js installed: $NODE_VERSION"
    
    # Extract major version number
    NODE_MAJOR=$(echo $NODE_VERSION | cut -d'.' -f1 | tr -d 'v')
    if [ "$NODE_MAJOR" -lt 18 ]; then
        echo "⚠️  Warning: Node.js 18+ recommended (you have v$NODE_MAJOR)"
    fi
else
    echo "❌ Node.js not found"
    echo "   Install from: https://nodejs.org/"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Check npm
echo "🔍 Checking npm..."
if command -v npm &> /dev/null; then
    NPM_VERSION=$(npm --version)
    echo "✅ npm installed: v$NPM_VERSION"
else
    echo "❌ npm not found"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Check FFmpeg
echo "🔍 Checking FFmpeg..."
if command -v ffmpeg &> /dev/null; then
    FFMPEG_VERSION=$(ffmpeg -version | head -n1)
    echo "✅ FFmpeg installed: $FFMPEG_VERSION"
    
    # Check for AAC codec
    if ffmpeg -codecs 2>&1 | grep -q "aac"; then
        echo "✅ AAC codec available"
    else
        echo "❌ AAC codec not found in FFmpeg"
        echo "   Reinstall FFmpeg with full codec support"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "❌ FFmpeg not found"
    echo "   macOS: brew install ffmpeg"
    echo "   Ubuntu: sudo apt install ffmpeg"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Check Docker (optional)
echo "🔍 Checking Docker (optional for SRS)..."
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version)
    echo "✅ Docker installed: $DOCKER_VERSION"
    
    # Check if SRS container is running
    if docker ps | grep -q "srs"; then
        echo "✅ SRS container is running"
    else
        echo "⚠️  SRS container not running"
        echo "   Start with: docker run -d -p 1935:1935 -p 8080:8080 --name srs ossrs/srs:5"
    fi
else
    echo "⚠️  Docker not found (optional, but recommended for SRS)"
    echo "   Install from: https://www.docker.com/get-started"
fi
echo ""

# Check if SRS is accessible
echo "🔍 Checking SRS server..."
if curl -s http://localhost:8080/api/v1/versions &> /dev/null; then
    echo "✅ SRS is accessible at http://localhost:8080"
else
    echo "⚠️  SRS not accessible at http://localhost:8080"
    echo "   Make sure SRS is running before starting the pipeline"
fi
echo ""

# Check project dependencies
echo "🔍 Checking project dependencies..."
if [ -d "node_modules" ]; then
    echo "✅ node_modules exists"
    
    # Check for key dependencies
    if [ -d "node_modules/m3u8stream" ]; then
        echo "✅ m3u8stream installed"
    else
        echo "❌ m3u8stream not found"
        ERRORS=$((ERRORS + 1))
    fi
    
    if [ -d "node_modules/m3u8-parser" ]; then
        echo "✅ m3u8-parser installed"
    else
        echo "❌ m3u8-parser not found"
        ERRORS=$((ERRORS + 1))
    fi
    
    if [ -d "node_modules/typescript" ]; then
        echo "✅ TypeScript installed"
    else
        echo "❌ TypeScript not found"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "⚠️  node_modules not found"
    echo "   Run: npm install"
fi
echo ""

# Summary
echo "════════════════════════════════════════════════════════════"
if [ $ERRORS -eq 0 ]; then
    echo "✅ All required dependencies are installed!"
    echo ""
    echo "Next steps:"
    echo "  1. Start SRS: docker run -d -p 1935:1935 -p 8080:8080 --name srs ossrs/srs:5"
    echo "  2. Run pipeline: npm run dev"
    echo "  3. Open index.html in browser"
else
    echo "❌ Found $ERRORS error(s)"
    echo ""
    echo "Please install missing dependencies before running the pipeline."
fi
echo "════════════════════════════════════════════════════════════"

