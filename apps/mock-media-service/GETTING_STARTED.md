# Getting Started with Mock Media Service

## What is this?

A WebSocket server that streams m4s audio fragments to clients. Perfect for testing audio processing pipelines without needing a full media server.

## 5-Minute Setup

### 1. Create Configuration

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

### 2. Add Test Audio Files

```bash
# Create a test stream
mkdir -p src/assets/audio-fragments/test-stream

# Add your m4s files (you need to provide these)
# cp /path/to/your/*.m4s src/assets/audio-fragments/test-stream/
```

### 3. Start the Service

```bash
cd ../..  # Back to repo root
npx nx serve mock-media-service
```

You should see:
```
Mock Media Service Configuration:
  Host: localhost
  Port: 4000
  Fragment Data Interval: 15000ms
  ...

[ ready ] Mock Media Service
  HTTP: http://localhost:4000
  WebSocket: ws://localhost:4000
  Fragments path: ...
```

### 4. Test It

**Option A: Quick health check**
```bash
curl http://localhost:4000/
```

**Option B: Test with the example client**
```bash
node apps/mock-media-service/example-client.js
```

## What Happens Next?

1. Client connects to `ws://localhost:4000`
2. Client subscribes: `socket.emit('subscribe', { streamId: 'test-stream' })`
3. Server sends 4 fragments, one every 15 seconds
4. After 4 fragments, server emits `stream:complete`
5. Server automatically disconnects the client

## Basic Client Example

```javascript
const { io } = require('socket.io-client');
const socket = io('ws://localhost:4000');

socket.on('connect', () => {
  console.log('Connected!');
  socket.emit('subscribe', { streamId: 'test-stream' });
});

socket.on('fragment:data', ({ fragment, data }) => {
  console.log(`Got fragment ${fragment.sequenceNumber}: ${data.length} bytes`);
  // Process your m4s data here
});

socket.on('stream:complete', () => {
  console.log('Done! Received all 4 fragments');
});
```

## Common Use Cases

### Testing an Audio Pipeline
```javascript
socket.on('fragment:data', async ({ fragment, data }) => {
  // Send to your processing pipeline
  await myPipeline.processM4S(data);
});
```

### Saving Fragments to Disk
```javascript
const fs = require('fs');

socket.on('fragment:data', ({ fragment, data }) => {
  fs.writeFileSync(`output-${fragment.sequenceNumber}.m4s`, data);
});
```

### Collecting All Fragments
```javascript
const fragments = [];

socket.on('fragment:data', ({ fragment, data }) => {
  fragments.push(data);
});

socket.on('stream:complete', () => {
  console.log(`Collected ${fragments.length} fragments`);
  // Process complete stream
});
```

## Configuration Tips

**Faster testing? Reduce the interval:**
```env
FRAGMENT_DATA_INTERVAL=5000  # 5 seconds instead of 15
```

**Need more fragments?**
```env
MAX_FRAGMENTS_PER_STREAM=10  # 10 fragments instead of 4
```

**Multiple streams?**
```bash
mkdir -p src/assets/audio-fragments/english
mkdir -p src/assets/audio-fragments/spanish
# Add m4s files to each...
```

## Troubleshooting

**"Stream not found"**
- Check: `curl http://localhost:4000/streams`
- Make sure your stream directory exists and has .m4s files

**"Connection refused"**
- Is the service running? `curl http://localhost:4000/`
- Check the port: default is 4000

**"No fragments being sent"**
- Look at the console logs
- Verify .m4s files exist in `src/assets/audio-fragments/{streamId}/`

## Next Steps

- **Production deployment?** See README.md for build instructions
- **API details?** Check README.md for complete WebSocket API
- **Customization?** Review IMPLEMENTATION_SUMMARY.md for architecture

## Need Help?

Check these files in order:
1. **QUICK_REFERENCE.md** - Command cheat sheet
2. **README.md** - Complete documentation
3. **SETUP.md** - Detailed setup guide
4. **example-client.js** - Working code example

## That's It!

You now have a running WebSocket service that streams m4s audio fragments. Perfect for testing your audio processing pipeline without the complexity of a full streaming server.

Happy streaming! 🎵

