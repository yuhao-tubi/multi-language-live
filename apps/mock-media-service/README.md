# Mock Media Service

A Socket.IO-based WebSocket server that delivers m4s audio fragments to consumers for testing and development.

## Overview

The Mock Media Service provides real-time streaming of audio fragments via WebSocket connections. It delivers exactly 4 fragments per subscription and then automatically disconnects the client.

## Features

- **WebSocket Transport**: Binary m4s fragment delivery via Socket.IO
- **Event-Based Architecture**: Subscribe/unsubscribe pattern with acknowledgments
- **Configurable Intervals**: Adjust fragment delivery timing via environment variables
- **Auto-Disconnect**: Delivers 4 fragments per stream then disconnects
- **Multiple Streams**: Support for multiple concurrent audio streams
- **Health Monitoring**: REST endpoints for service status and available streams

## Configuration

Create a `.env` file in the `apps/mock-media-service/` directory with the following variables:

```env
HOST=localhost
PORT=4000
FRAGMENT_DATA_INTERVAL=15000
ACK_TIMEOUT_MS=5000
MAX_RETRIES=3
MAX_FRAGMENTS_PER_STREAM=4
```

### Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `localhost` | Server host address |
| `PORT` | `4000` | Server port (static) |
| `FRAGMENT_DATA_INTERVAL` | `15000` | Interval between fragment deliveries (ms) |
| `ACK_TIMEOUT_MS` | `5000` | Timeout for fragment acknowledgment (ms) |
| `MAX_RETRIES` | `3` | Maximum retry attempts for failed deliveries |
| `MAX_FRAGMENTS_PER_STREAM` | `4` | Number of fragments to deliver before auto-disconnect |

## Setup

### 1. Install Dependencies

Dependencies are managed at the monorepo root level. From the workspace root:

```bash
npm install
```

### 2. Add Audio Fragments

Place your m4s audio fragment files in the following structure:

```
apps/mock-media-service/src/assets/audio-fragments/
└── {streamId}/
    ├── fragment-0.m4s
    ├── fragment-1.m4s
    ├── fragment-2.m4s
    └── fragment-3.m4s
```

Each directory under `audio-fragments/` represents a stream identified by its folder name.

### 3. Create .env File

Copy the configuration above and save it as `.env` in `apps/mock-media-service/`.

## Running the Service

### Development Mode

```bash
nx serve mock-media-service
```

### Production Build

```bash
nx build mock-media-service
cd dist/mock-media-service
npm install
node main.js
```

## API Reference

### REST Endpoints

#### Health Check
```
GET http://localhost:4000/
```

Response:
```json
{
  "message": "Mock Media Service",
  "status": "running",
  "stats": {
    "activeStreams": 1,
    "totalSubscribers": 2
  }
}
```

#### List Available Streams
```
GET http://localhost:4000/streams
```

Response:
```json
{
  "streams": ["stream1", "stream2"]
}
```

### WebSocket Events

Connect to: `ws://localhost:4000`

#### Client → Server Events

**Subscribe to a stream:**
```javascript
socket.emit('subscribe', { streamId: 'stream1' });
```

**Unsubscribe from a stream:**
```javascript
socket.emit('unsubscribe', { streamId: 'stream1' });
```

**Acknowledge fragment receipt:**
```javascript
socket.emit('fragment:ack', { fragmentId: 'stream1-0' });
```

#### Server → Client Events

**Subscription confirmed:**
```javascript
socket.on('subscribed', (data) => {
  console.log('Subscribed to:', data.streamId);
});
```

**Fragment data received:**
```javascript
socket.on('fragment:data', (delivery) => {
  const { fragment, data } = delivery;
  // fragment: AudioFragment metadata
  // data: Buffer containing m4s binary data
  console.log(`Received fragment ${fragment.sequenceNumber}`, data.length, 'bytes');
});
```

**Stream completed (4 fragments delivered):**
```javascript
socket.on('stream:complete', (data) => {
  console.log('Stream completed:', data.streamId);
  // Server will disconnect socket after this event
});
```

**Error occurred:**
```javascript
socket.on('error', (error) => {
  console.error('Error:', error.message);
});
```

**Unsubscribed:**
```javascript
socket.on('unsubscribed', (data) => {
  console.log('Unsubscribed from:', data.streamId);
});
```

## Data Structures

### AudioFragment

```typescript
interface AudioFragment {
  id: string;              // Unique fragment ID (e.g., "stream1-0")
  streamId: string;        // Stream identifier
  sequenceNumber: number;  // Fragment sequence (0-3)
  timestamp: number;       // Unix timestamp (ms)
  duration: number;        // Fragment duration (ms)
  codec: string;           // Audio codec (e.g., "aac")
  sampleRate: number;      // Sample rate (Hz)
  channels: number;        // Number of channels
  bitrate: number;         // Bitrate (bps)
  metadata?: {             // Optional metadata
    fileName: string;
    fileSize: number;
  };
}
```

### FragmentDelivery

```typescript
interface FragmentDelivery {
  fragment: AudioFragment;  // Fragment metadata
  data: Buffer;             // m4s binary data
}
```

## Example Client

```javascript
import { io } from 'socket.io-client';

const socket = io('ws://localhost:4000');

socket.on('connect', () => {
  console.log('Connected to mock media service');
  
  // Subscribe to a stream
  socket.emit('subscribe', { streamId: 'stream1' });
});

socket.on('subscribed', (data) => {
  console.log('✓ Subscribed to:', data.streamId);
});

socket.on('fragment:data', (delivery) => {
  const { fragment, data } = delivery;
  console.log(`Fragment ${fragment.sequenceNumber + 1}/4:`, {
    id: fragment.id,
    size: data.length,
    timestamp: fragment.timestamp
  });
  
  // Acknowledge receipt
  socket.emit('fragment:ack', { fragmentId: fragment.id });
});

socket.on('stream:complete', (data) => {
  console.log('✓ Stream completed:', data.streamId);
  console.log('Server will disconnect socket...');
});

socket.on('disconnect', (reason) => {
  console.log('Disconnected:', reason);
});

socket.on('error', (error) => {
  console.error('Error:', error);
});
```

## Architecture

### Components

- **FragmentProvider**: Reads m4s files from disk and emits fragments on a configurable interval
- **StreamManager**: Manages subscriptions and coordinates between FragmentProvider and Socket.IO
- **Socket Handlers**: Handles WebSocket events (subscribe, unsubscribe, ack)

### Event Flow

```
1. Client connects via WebSocket
2. Client emits 'subscribe' with streamId
3. Server validates stream exists
4. Server adds client to room and starts stream
5. Server emits 'fragment:data' every FRAGMENT_DATA_INTERVAL
6. Client receives fragment and emits 'fragment:ack'
7. After 4 fragments, server emits 'stream:complete'
8. Server disconnects client automatically
```

## Troubleshooting

### "No m4s files found for stream"

Ensure you have m4s files in the correct directory:
```
apps/mock-media-service/src/assets/audio-fragments/{streamId}/*.m4s
```

### "Stream not found"

Check available streams via `GET http://localhost:4000/streams` or verify the `audio-fragments` directory contains subdirectories with m4s files.

### Port already in use

If port 4000 is in use, update the `PORT` variable in your `.env` file.

### Fragments not cycling correctly

If you have fewer than 4 m4s files, the service will cycle through them. Ensure you have at least 4 unique fragment files for complete testing.

## Development

### Project Structure

```
apps/mock-media-service/
├── src/
│   ├── main.ts                         # Server entry point
│   ├── types/
│   │   └── index.ts                    # TypeScript interfaces
│   ├── services/
│   │   ├── fragment-provider.service.ts # Fragment delivery logic
│   │   └── stream-manager.service.ts    # Subscription management
│   ├── handlers/
│   │   └── socket.handler.ts           # Socket.IO event handlers
│   └── assets/
│       └── audio-fragments/            # m4s files organized by stream
├── .env                                # Configuration (not in git)
├── project.json                        # NX project config
└── README.md                           # This file
```

### Adding a New Stream

1. Create a directory: `src/assets/audio-fragments/my-new-stream/`
2. Add m4s files: `fragment-0.m4s`, `fragment-1.m4s`, etc.
3. Restart the service
4. Subscribe via WebSocket: `socket.emit('subscribe', { streamId: 'my-new-stream' })`

## License

ISC

