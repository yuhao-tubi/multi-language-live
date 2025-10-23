# Mock Media Service - Testing Guide

## Prerequisites

Make sure you have:
1. ✓ `.env` file created in `apps/mock-media-service/`
2. ✓ Socket.IO client installed: `npm install socket.io-client`
3. ✓ Test audio fragments in `src/assets/audio-fragments/test-stream/`

## Quick Verification Steps

### Step 1: Verify Configuration

```bash
# Check .env file exists
cat apps/mock-media-service/.env

# Should show:
# HOST=localhost
# PORT=4000
# STREAM_ID=test-stream
# ...
```

### Step 2: Create Test Stream Directory

```bash
# Create the test stream directory
mkdir -p apps/mock-media-service/src/assets/audio-fragments/test-stream

# Add your m4s files (you'll need to provide these)
# Example: cp /path/to/your/*.m4s apps/mock-media-service/src/assets/audio-fragments/test-stream/
```

### Step 3: Start the Mock Media Service

**Terminal 1:**
```bash
npx nx serve mock-media-service
```

You should see:
```
Mock Media Service Configuration:
  Host: localhost
  Port: 4000
  Fragment Data Interval: 15000ms
  ACK Timeout: 5000ms
  Max Retries: 3
  Max Fragments Per Stream: 4

[ ready ] Mock Media Service
  HTTP: http://localhost:4000
  WebSocket: ws://localhost:4000
```

### Step 4: Verify Server is Running

**Terminal 2:**
```bash
# Test HTTP health endpoint
curl http://localhost:4000/

# Should return:
# {"message":"Mock Media Service","status":"running","stats":{...}}

# List available streams
curl http://localhost:4000/streams

# Should return:
# {"streams":["test-stream"]}
```

### Step 5: Run Test Subscriber

**Option A: Basic Example Client**
```bash
node apps/mock-media-service/example-client.js
```

**Option B: Detailed Test Subscriber (Recommended)**
```bash
node apps/mock-media-service/test-subscriber.js
```

**Option C: Test Different Stream**
```bash
node apps/mock-media-service/test-subscriber.js my-other-stream
```

## Test Client Comparison

### example-client.js
- ✓ Simple, easy to read
- ✓ Basic logging
- ✓ Good for quick tests
- ✓ Shows fragment data and acknowledgments

### test-subscriber.js (Detailed)
- ✓ Comprehensive logging with timestamps
- ✓ Color-coded output
- ✓ Connection metrics and timing analysis
- ✓ Fragment interval statistics
- ✓ Data validation (checks for Buffer, m4s signature)
- ✓ Optional fragment saving to disk
- ✓ Detailed error reporting
- ✓ Final summary with statistics
- ✓ Troubleshooting guidance on errors

## Expected Output Flow

### 1. Connection Phase
```
[2025-10-23T...] [CONNECT] Initiating connection to server...
[2025-10-23T...] [SUCCESS] Connected to server
```

### 2. Subscription Phase
```
[2025-10-23T...] [SUBSCRIBE] Requesting subscription to stream: test-stream
[2025-10-23T...] [SUCCESS] Successfully subscribed to stream
[2025-10-23T...] [WAITING] Waiting for fragments...
```

### 3. Fragment Delivery (4 fragments)
```
[2025-10-23T...] [RECEIVED] Fragment data received
[2025-10-23T...] [VALIDATE] Data validation passed: Buffer type confirmed
[2025-10-23T...] [ACK] Acknowledgment sent
```

### 4. Stream Completion
```
[2025-10-23T...] [COMPLETE] Stream completed successfully
[2025-10-23T...] [DISCONNECT] Disconnected from server
```

## Advanced Testing Options

### Save Fragments to Disk

Set environment variable to save received fragments:

```bash
SAVE_FRAGMENTS=true node apps/mock-media-service/test-subscriber.js
```

Fragments will be saved to: `apps/mock-media-service/output/`

### Test Faster Delivery

Modify `.env` to test with faster intervals:

```env
FRAGMENT_DATA_INTERVAL=5000  # 5 seconds instead of 15
```

Restart the server and run the test again.

### Test More Fragments

```env
MAX_FRAGMENTS_PER_STREAM=10  # 10 fragments instead of 4
```

## What to Look For

### ✅ Success Indicators

1. **Connection succeeds** - Socket ID is displayed
2. **Subscription confirmed** - "Successfully subscribed" message
3. **Fragments arrive** - 4 fragments received at ~15 second intervals
4. **Proper timing** - Intervals are consistent (~15000ms each)
5. **Data validation passes** - Buffer type confirmed
6. **Stream completes** - "Stream completed successfully"
7. **Auto-disconnect** - Client disconnects after 4 fragments

### ⚠️ Warning Signs

1. **Irregular intervals** - Large variance in fragment timing
2. **Wrong fragment count** - Not receiving 4 fragments
3. **Data corruption** - Invalid Buffer or wrong sizes
4. **No auto-disconnect** - Client stays connected after 4 fragments

### ❌ Common Errors

#### "Connection refused"
```
[ERROR] Failed to connect to server
```
**Solution:** Make sure the server is running (`npx nx serve mock-media-service`)

#### "Stream not found"
```
[ERROR] Stream test-stream not found
```
**Solution:** 
- Check available streams: `curl http://localhost:4000/streams`
- Verify directory exists: `ls apps/mock-media-service/src/assets/audio-fragments/`
- Add m4s files to the stream directory

#### "No m4s files found"
**Solution:**
```bash
# Add m4s files to your stream directory
cp /path/to/fragments/*.m4s apps/mock-media-service/src/assets/audio-fragments/test-stream/
```

#### "Data validation failed"
**Solution:** This indicates data corruption. Check:
- Are the m4s files valid?
- Is the Buffer size reasonable?
- Check server logs for errors

## Metrics to Verify

When running `test-subscriber.js`, verify these metrics:

### Connection Metrics
- Connection time: < 100ms (typically)
- Time to first fragment: < 100ms after subscription
- Total fragments: 4
- Total bytes: Should match sum of your m4s file sizes

### Fragment Intervals
- Min interval: ~15000ms
- Max interval: ~15000ms
- Avg interval: ~15000ms
- Std deviation: < 100ms (low variance is good)

## Multiple Client Testing

Test multiple clients subscribing to the same stream:

**Terminal 3:**
```bash
node apps/mock-media-service/test-subscriber.js test-stream
```

**Terminal 4:**
```bash
node apps/mock-media-service/test-subscriber.js test-stream
```

Both clients should receive the same fragments simultaneously.

## Troubleshooting Checklist

If tests fail, check in this order:

- [ ] Server is running: `curl http://localhost:4000/`
- [ ] .env file exists and has correct values
- [ ] Stream directory exists: `ls apps/mock-media-service/src/assets/audio-fragments/test-stream/`
- [ ] At least one .m4s file exists in stream directory
- [ ] Port 4000 is not blocked by firewall
- [ ] Socket.IO client is installed: `npm list socket.io-client`
- [ ] No port conflicts (check if port 4000 is in use)

## Automated Test Script

Create a simple automated test:

```bash
#!/bin/bash
# test-mock-service.sh

echo "Starting mock media service in background..."
npx nx serve mock-media-service &
SERVER_PID=$!

sleep 5

echo "Testing health endpoint..."
curl http://localhost:4000/

echo "Running test subscriber..."
node apps/mock-media-service/test-subscriber.js

echo "Stopping server..."
kill $SERVER_PID
```

## Next Steps

Once basic testing works:
1. Test with your actual m4s audio files
2. Integrate with your audio processing pipeline
3. Test error scenarios (disconnect, invalid streams, etc.)
4. Performance testing with multiple concurrent clients
5. Test with different FRAGMENT_DATA_INTERVAL values

## Getting Help

If you encounter issues:
1. Check server logs in Terminal 1
2. Review the detailed output from test-subscriber.js
3. Verify all configuration in .env file
4. Check the main README.md for API details
5. Review IMPLEMENTATION_SUMMARY.md for architecture details

