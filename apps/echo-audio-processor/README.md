# Echo Audio Processor

A simple test service that echoes audio fragments back to the sender. Used for testing the live-media-service without requiring actual audio processing.

## Features

- ✅ Socket.IO server on port 5000
- ✅ Receives audio fragments via WebSocket
- ✅ Echoes fragments back after 100ms delay
- ✅ Logs all activity with timestamps
- ✅ Statistics reporting every 30 seconds

## Quick Start

```bash
# Install dependencies
npm install

# Run in development mode
npm run dev

# Build for production
npm run build

# Run production build
npm start
```

## Protocol

The service implements the same WebSocket protocol as defined in `mock-media-service/PROTOCOL.md`:

### Receive Fragment

**Event:** `fragment:data`

```typescript
{
  fragment: {
    id: string;
    streamId: string;
    batchNumber: number;
    contentType: string;
    size: number;
    duration: number;
    timestamp: string;
  },
  data: Buffer;
}
```

### Send Processed Fragment

**Event:** `fragment:processed`

```typescript
{
  fragment: FragmentMetadata; // Same as received
  data: Buffer; // Same as received (echo)
  metadata: {
    processingTime: number;
    processor: string;
    timestamp: string;
  }
}
```

## Testing

Connect to `http://localhost:5000` with Socket.IO client:

```javascript
import { io } from 'socket.io-client';

const socket = io('http://localhost:5000');

socket.on('connect', () => {
  console.log('Connected');
  
  // Send test fragment
  socket.emit('fragment:data', {
    fragment: {
      id: 'test-1',
      streamId: 'test-stream',
      batchNumber: 0,
      contentType: 'audio/mp4',
      size: 1024,
      duration: 30,
      timestamp: new Date().toISOString(),
    },
    data: Buffer.from('test audio data'),
  });
});

socket.on('fragment:processed', (event) => {
  console.log('Received processed fragment:', event.fragment.id);
});
```

## Configuration

- **Port:** 5000 (configurable in `src/main.ts`)
- **Echo Delay:** 100ms (simulates processing time)
- **Max Buffer Size:** 50MB (for large audio fragments)

## Use Case

This service is designed for:
- Testing live-media-service without external dependencies
- Development and debugging
- Integration tests
- Performance benchmarking

