#!/bin/bash

# Test Helper Script for Live Audio Stream Client
# This script helps test the stream_audio_client.py with the mock-media-service

set -e

# Configuration
MOCK_SERVICE_URL="http://localhost:4000"
MOCK_SERVICE_WS="ws://localhost:4000"
DEFAULT_STREAM_ID="stream-1"
DEFAULT_TARGETS="es"

echo "========================================"
echo "Live Audio Stream Client Test Helper"
echo "========================================"

# Function to check if mock-media-service is running
check_mock_service() {
    echo "Checking if mock-media-service is running..."
    
    if curl -s "$MOCK_SERVICE_URL" > /dev/null 2>&1; then
        echo "✓ Mock-media-service is running"
        return 0
    else
        echo "✗ Mock-media-service is not running"
        return 1
    fi
}

# Function to list available streams
list_streams() {
    echo "Fetching available streams..."
    
    if streams=$(curl -s "$MOCK_SERVICE_URL/streams" 2>/dev/null); then
        echo "Available streams:"
        echo "$streams" | jq -r '.streams[]' 2>/dev/null || echo "$streams"
    else
        echo "Failed to fetch streams"
    fi
}

# Function to check Python environment
check_python_env() {
    echo "Checking Python environment..."
    
    # Check if we're in a conda environment
    if [[ -n "$CONDA_DEFAULT_ENV" ]]; then
        echo "✓ Conda environment: $CONDA_DEFAULT_ENV"
    else
        echo "! Not in a conda environment"
    fi
    
    # Check required Python packages
    local missing_packages=()
    
    if ! python -c "import socketio" 2>/dev/null; then
        missing_packages+=("python-socketio")
    fi
    
    if ! python -c "import rich" 2>/dev/null; then
        missing_packages+=("rich")
    fi
    
    if ! python -c "import numpy" 2>/dev/null; then
        missing_packages+=("numpy")
    fi
    
    if ! python -c "import soundfile" 2>/dev/null; then
        missing_packages+=("soundfile")
    fi
    
    if [[ ${#missing_packages[@]} -eq 0 ]]; then
        echo "✓ All required Python packages are installed"
    else
        echo "✗ Missing packages: ${missing_packages[*]}"
        echo "Install with: conda env update -f environment.yml"
        return 1
    fi
}

# Function to check voice configuration
check_voice_config() {
    echo "Checking voice configuration..."
    
    if [[ -f "coqui-voices.yaml" ]]; then
        echo "✓ Voice configuration file found"
        
        # Check if configured languages exist
        local configured_langs=$(python -c "
import yaml
try:
    with open('coqui-voices.yaml', 'r') as f:
        cfg = yaml.safe_load(f)
    langs = list(cfg.get('languages', {}).keys())
    print(' '.join(langs))
except Exception as e:
    print('')
")
        
        if [[ -n "$configured_langs" ]]; then
            echo "✓ Configured languages: $configured_langs"
        else
            echo "! No languages configured in coqui-voices.yaml"
        fi
    else
        echo "✗ Voice configuration file not found"
        echo "Create coqui-voices.yaml with language configurations"
        return 1
    fi
}

# Function to start mock-media-service
start_mock_service() {
    echo "Starting mock-media-service..."
    
    # Check if we're in the right directory
    if [[ ! -f "../../package.json" ]]; then
        echo "✗ Not in the correct directory. Run from apps/sts-service/"
        return 1
    fi
    
    # Start the service in background with output redirected
    cd ../..
    echo "Starting mock-media-service in background (output redirected)..."
    npx nx serve mock-media-service > /dev/null 2>&1 &
    local service_pid=$!
    cd apps/sts-service
    
    echo "✓ Started mock-media-service (PID: $service_pid)"
    echo "  (Service output redirected to avoid terminal interference)"
    
    # Wait for service to start
    echo "Waiting for service to start..."
    local attempts=0
    while [[ $attempts -lt 30 ]]; do
        if curl -s "$MOCK_SERVICE_URL" > /dev/null 2>&1; then
            echo "✓ Service is ready"
            return 0
        fi
        sleep 1
        ((attempts++))
    done
    
    echo "✗ Service failed to start within 30 seconds"
    return 1
}

# Function to stop mock-media-service
stop_mock_service() {
    echo "Stopping mock-media-service..."
    
    # Find and kill the service process
    local pids=$(pgrep -f "nx serve mock-media-service" 2>/dev/null || true)
    
    if [[ -n "$pids" ]]; then
        echo "$pids" | xargs kill 2>/dev/null || true
        echo "✓ Stopped mock-media-service"
    else
        echo "! No mock-media-service process found"
    fi
}

# Function to run the stream client
run_stream_client() {
    local stream_id="${1:-$DEFAULT_STREAM_ID}"
    local targets="${2:-$DEFAULT_TARGETS}"
    local save_local="${3:-false}"
    
    echo "Running stream client..."
    echo "Stream ID: $stream_id"
    echo "Targets: $targets"
    echo "Save locally: $save_local"
    echo ""
    
    local cmd="python stream_audio_client.py --stream-id $stream_id --targets $targets"
    
    if [[ "$save_local" == "true" ]]; then
        cmd="$cmd --save-local"
    fi
    
    echo "Command: $cmd"
    echo ""
    
    eval "$cmd"
}

# Function to run simple acknowledgment test
run_ack_test() {
    echo "Running simple acknowledgment test..."
    echo "This test only acknowledges fragments without processing them"
    echo ""
    
    python test_ack_client.py
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [command] [options]"
    echo ""
    echo "Commands:"
    echo "  check          - Check environment and dependencies"
    echo "  start-service  - Start mock-media-service (background, output redirected)"
    echo "  stop-service   - Stop mock-media-service"
    echo "  list-streams   - List available streams"
    echo "  run [stream] [targets] [save] - Run stream client"
    echo "  ack-test       - Run simple acknowledgment test (no processing)"
    echo "  test           - Run full test (check + start + run)"
    echo "  help           - Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 check"
    echo "  $0 start-service"
    echo "  $0 stop-service"
    echo "  $0 ack-test"
    echo "  $0 run stream-1 es true"
    echo "  $0 test"
    echo ""
}

# Function to run full test
run_full_test() {
    echo "Running full test..."
    
    # Check environment
    if ! check_python_env; then
        echo "Environment check failed"
        return 1
    fi
    
    if ! check_voice_config; then
        echo "Voice config check failed"
        return 1
    fi
    
    # Check or start service
    if ! check_mock_service; then
        echo "Starting mock-media-service..."
        if ! start_mock_service; then
            echo "Failed to start mock-media-service"
            return 1
        fi
    fi
    
    # List streams
    list_streams
    
    # Run client
    echo "Starting stream client test..."
    run_stream_client "$DEFAULT_STREAM_ID" "$DEFAULT_TARGETS" "true"
}

# Main script logic
case "${1:-help}" in
    "check")
        check_python_env
        check_voice_config
        check_mock_service
        ;;
    "start-service")
        start_mock_service
        ;;
    "stop-service")
        stop_mock_service
        ;;
    "list-streams")
        if check_mock_service; then
            list_streams
        fi
        ;;
    "run")
        if check_mock_service; then
            run_stream_client "$2" "$3" "$4"
        fi
        ;;
    "ack-test")
        if check_mock_service; then
            run_ack_test
        fi
        ;;
    "test")
        run_full_test
        ;;
    "help"|*)
        show_usage
        ;;
esac
