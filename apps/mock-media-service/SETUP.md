# Mock Media Service Setup Guide

## Quick Start

### 1. Create Environment Configuration

Create a `.env` file in `apps/mock-media-service/`:

```bash
cd apps/mock-media-service
cat > .env << 'EOF'
HOST=localhost
PORT=4000
FRAGMENT_DATA_INTERVAL=15000
ACK_TIMEOUT_MS=5000
MAX_RETRIES=3
MAX_FRAGMENTS_PER_STREAM=4
EOF
```

Or create it manually with your preferred editor:

```bash
nano apps/mock-media-service/.env
```

### 2. Add Test Audio Fragments

Create a test stream directory and add your m4s files:

```bash
# Create test stream directory
mkdir -p apps/mock-media-service/src/assets/audio-fragments/stream-1

# Add your m4s files (example - replace with your actual files)
# cp /path/to/your/fragments/*.m4s apps/mock-media-service/src/assets/audio-fragments/stream-1/
```

**Directory structure should look like:**
```
apps/mock-media-service/src/assets/audio-fragments/
└── stream-1/              # Stream ID = directory name
    ├── fragment-0.m4s
    ├── fragment-1.m4s
    ├── fragment-2.m4s
    └── fragment-3.m4s
```

### 3. Install Dependencies

From the monorepo root:

```bash
npm install
```

### 4. Start the Service

```bash
# Development mode with auto-reload
npx nx serve mock-media-service

# Or build and run production
npx nx build mock-media-service
cd dist/mock-media-service
npm install
node main.js
```

**Note:** Assets (audio fragments) are automatically copied during build. The service will look for fragments at `dist/mock-media-service/assets/audio-fragments/`. No manual copying needed!

### 5. Test the Service

**Option A: Using the example client**

```bash
# Install socket.io-client if not already installed
npm install socket.io-client --save-dev

# Run the example client
node apps/mock-media-service/example-client.js
```

**Option B: Using curl for REST endpoints**

```bash
# Health check
curl http://localhost:4000/

# List available streams
curl http://localhost:4000/streams
```

**Option C: Using your own client**

See `README.md` for WebSocket API documentation and `example-client.js` for implementation reference.

## Configuration Details

### Environment Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `HOST` | string | `localhost` | Server bind address |
| `PORT` | number | `4000` | Server port (should remain 4000) |
| `FRAGMENT_DATA_INTERVAL` | number | `15000` | Milliseconds between fragments |
| `ACK_TIMEOUT_MS` | number | `5000` | Acknowledgment timeout |
| `MAX_RETRIES` | number | `3` | Maximum retry attempts |
| `MAX_FRAGMENTS_PER_STREAM` | number | `4` | Fragments before auto-disconnect |

### Adjusting Fragment Delivery Speed

To send fragments faster (e.g., for testing):

```env
# Send fragments every 5 seconds instead of 15
FRAGMENT_DATA_INTERVAL=5000
```

To send more/fewer fragments before disconnect:

```env
# Send 10 fragments instead of 4
MAX_FRAGMENTS_PER_STREAM=10
```

## Adding Multiple Streams

Create multiple directories under `audio-fragments/`:

```bash
# Stream 1: English
mkdir -p apps/mock-media-service/src/assets/audio-fragments/english-stream
# Add m4s files to english-stream/

# Stream 2: Spanish  
mkdir -p apps/mock-media-service/src/assets/audio-fragments/spanish-stream
# Add m4s files to spanish-stream/

# Stream 3: French
mkdir -p apps/mock-media-service/src/assets/audio-fragments/french-stream
# Add m4s files to french-stream/
```

Then subscribe to each stream:

```javascript
socket.emit('subscribe', { streamId: 'english-stream' });
socket.emit('subscribe', { streamId: 'spanish-stream' });
socket.emit('subscribe', { streamId: 'french-stream' });
```

## Verifying Setup

Run this checklist to verify everything is configured:

```bash
# 1. Check .env exists
ls -la apps/mock-media-service/.env

# 2. Check audio fragments directory
ls -R apps/mock-media-service/src/assets/audio-fragments/

# 3. Verify build works
npx nx build mock-media-service

# 4. Check available streams
curl http://localhost:4000/streams
```

Expected output for step 4 (with stream-1):
```json
{
  "streams": ["stream-1"]
}
```

## Troubleshooting

### "Cannot find module 'dotenv'"

Run `npm install` from the monorepo root.

### "Fragments directory does not exist"

Ensure the path exists:
```bash
mkdir -p apps/mock-media-service/src/assets/audio-fragments
```

### "Stream not found" error

- Verify stream directory exists: `ls apps/mock-media-service/src/assets/audio-fragments/`
- Check directory name matches the `streamId` you're subscribing to
- Ensure directory contains at least one `.m4s` file

### Port 4000 already in use

Change the PORT in `.env`:
```env
PORT=4001
```

And update your client connection URL accordingly.

### No fragments being sent

Check logs for:
- "No m4s files found" - add m4s files to the stream directory
- "Stream {id} is already active" - only one subscription per stream is active at a time
- File permission errors - ensure the process can read the m4s files

## Next Steps

1. ✓ Setup complete
2. Read `README.md` for API documentation
3. Examine `example-client.js` for integration examples
4. Integrate with your application using Socket.IO client library
5. Configure `FRAGMENT_DATA_INTERVAL` to match your requirements

## Need Help?

- Check the main `README.md` for detailed API documentation
- Review `example-client.js` for a working client implementation
- Verify all environment variables are set correctly in `.env`
- Ensure m4s files are in the correct directory structure

