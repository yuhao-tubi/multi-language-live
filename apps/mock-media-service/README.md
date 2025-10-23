# Mock Media Service

A WebSocket server that streams m4s audio fragments to clients for testing audio processing pipelines.

## Quick Start

### 1. Configure
```bash
cd apps/mock-media-service
cp .env.example .env
```

### 2. Add Audio Files
```bash
mkdir -p src/assets/audio-fragments/test-stream
# Add your *.m4s files to the directory above
```

### 3. Start Service
```bash
cd ../..  # Back to repo root
npx nx serve mock-media-service
```

### 4. Test
```bash
# Health check
curl http://localhost:4000/

# Run example client
node apps/mock-media-service/example-client.js
```

## Features

- WebSocket transport via Socket.IO
- Delivers 4 fragments per subscription, then auto-disconnects
- Configurable delivery intervals
- Multiple concurrent streams
- Health monitoring endpoints

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `localhost` | Server host address |
| `PORT` | `4000` | Server port |
| `FRAGMENT_DATA_INTERVAL` | `15000` | Interval between fragments (ms) |
| `ACK_TIMEOUT_MS` | `5000` | Acknowledgment timeout (ms) |
| `MAX_RETRIES` | `3` | Max retry attempts |
| `MAX_FRAGMENTS_PER_STREAM` | `4` | Fragments before auto-disconnect |

## Protocol Documentation

For detailed protocol specification, message formats, flow diagrams, and implementation guidelines, see **[PROTOCOL.md](PROTOCOL.md)**.

## API

### REST Endpoints

**Health Check:** `GET http://localhost:4000/`
```json
{
  "message": "Mock Media Service",
  "status": "running",
  "stats": { "activeStreams": 1, "totalSubscribers": 2 }
}
```

**List Streams:** `GET http://localhost:4000/streams`
```json
{
  "streams": ["test-stream", "stream-1"]
}
```

### WebSocket Events

**Connect:** `ws://localhost:4000`

**Client → Server:**
```javascript
socket.emit('subscribe', { streamId: 'test-stream' });
socket.emit('fragment:ack', { fragmentId: 'test-stream-0' });
socket.emit('unsubscribe', { streamId: 'test-stream' });
```

**Server → Client:**
```javascript
socket.on('subscribed', (data) => { /* Subscription confirmed */ });
socket.on('fragment:data', ({ fragment, data }) => { /* Fragment received */ });
socket.on('stream:complete', (data) => { /* All fragments delivered */ });
socket.on('error', (error) => { /* Error occurred */ });
```

## Example Client

```javascript
const { io } = require('socket.io-client');
const socket = io('ws://localhost:4000');

socket.on('connect', () => {
  socket.emit('subscribe', { streamId: 'test-stream' });
});

socket.on('fragment:data', ({ fragment, data }) => {
  console.log(`Fragment ${fragment.sequenceNumber}: ${data.length} bytes`);
  socket.emit('fragment:ack', { fragmentId: fragment.id });
});

socket.on('stream:complete', () => {
  console.log('Done! Received all fragments');
});
```

## Data Structures

```typescript
interface AudioFragment {
  id: string;              // "test-stream-0"
  streamId: string;        // "test-stream"
  sequenceNumber: number;  // 0-3
  timestamp: number;       // Unix timestamp (ms)
  duration: number;        // Fragment duration (ms)
  codec: string;           // "aac"
  sampleRate: number;      // Hz
  channels: number;        // Audio channels
  bitrate: number;         // bps
  metadata?: {
    fileName: string;
    fileSize: number;
  };
}

interface FragmentDelivery {
  fragment: AudioFragment;
  data: Buffer;  // m4s binary data
}
```

## Testing

### Verify Setup
```bash
# Check configuration
cat apps/mock-media-service/.env

# Verify streams are available
curl http://localhost:4000/streams

# Run test client
node apps/mock-media-service/test-subscriber.js
```

### Expected Flow
1. Client connects → `connect` event
2. Client subscribes → `subscribed` event
3. Server sends 4 fragments every 15s → `fragment:data` events
4. Stream completes → `stream:complete` event
5. Server auto-disconnects client

### Success Indicators
- ✓ Connection succeeds with socket ID
- ✓ 4 fragments received at ~15s intervals
- ✓ Data is valid Buffer type
- ✓ Stream completes and auto-disconnects

## Troubleshooting

**"Connection refused"**
- Ensure service is running: `curl http://localhost:4000/`
- Check port 4000 is available

**"Stream not found"**
- List streams: `curl http://localhost:4000/streams`
- Verify directory exists: `src/assets/audio-fragments/{streamId}/`
- Add .m4s files to stream directory

**"No fragments sent"**
- Check at least 4 .m4s files exist in stream directory
- Verify .env configuration is correct
- Review server console logs

## Project Structure

```
apps/mock-media-service/
├── src/
│   ├── main.ts                         # Server entry
│   ├── services/
│   │   ├── fragment-provider.service.ts # Fragment delivery
│   │   └── stream-manager.service.ts    # Subscription management
│   ├── handlers/
│   │   └── socket.handler.ts           # WebSocket handlers
│   └── assets/
│       └── audio-fragments/            # m4s files by stream
│           └── {streamId}/
│               ├── fragment-0.m4s
│               ├── fragment-1.m4s
│               └── ...
├── .env                                # Configuration
├── example-client.js                   # Basic client
└── test-subscriber.js                  # Detailed test client
```

## Adding a Stream

1. Create directory: `src/assets/audio-fragments/my-stream/`
2. Add .m4s files: `fragment-0.m4s`, `fragment-1.m4s`, etc.
3. Restart service
4. Subscribe: `socket.emit('subscribe', { streamId: 'my-stream' })`

## Production Build

```bash
nx build mock-media-service
cd dist/mock-media-service
npm install
node main.js
```

## License

ISC
