/**
 * Echo Audio Processor - Simple test service
 * Receives audio fragments and echoes them back after a short delay
 */
import { Server, Socket } from 'socket.io';

const PORT = 5000;
const ECHO_DELAY_MS = 100; // Simulate processing time

/**
 * Fragment metadata from protocol
 */
interface FragmentMetadata {
  id: string;
  streamId: string;
  batchNumber: number;
  contentType: string;
  size: number;
  duration: number;
  timestamp: string;
}

/**
 * Fragment data event
 */
interface FragmentDataEvent {
  fragment: FragmentMetadata;
  data: Buffer;
}

/**
 * Create Socket.IO server
 */
const io = new Server(PORT, {
  cors: {
    origin: '*',
    methods: ['GET', 'POST']
  },
  maxHttpBufferSize: 50 * 1024 * 1024, // 50MB max buffer size
});

console.log(`🎙️  Echo Audio Processor starting...`);
console.log(`📡 Listening on port ${PORT}`);
console.log(`⏱️  Echo delay: ${ECHO_DELAY_MS}ms\n`);

// Statistics
let stats = {
  connections: 0,
  fragmentsReceived: 0,
  fragmentsEchoed: 0,
  totalBytesReceived: 0,
  totalBytesEchoed: 0,
  startTime: new Date(),
};

/**
 * Handle client connection
 */
io.on('connection', (socket: Socket) => {
  stats.connections++;
  
  console.log(`[${new Date().toISOString()}] ✅ Client connected: ${socket.id}`);
  console.log(`   Total connections: ${stats.connections}\n`);

  /**
   * Handle fragment data
   */
  socket.on('fragment:data', (event: FragmentDataEvent) => {
    const { fragment, data } = event;
    
    stats.fragmentsReceived++;
    stats.totalBytesReceived += data.length;

    console.log(`[${new Date().toISOString()}] 📥 Received fragment:`);
    console.log(`   ID: ${fragment.id}`);
    console.log(`   Stream: ${fragment.streamId}`);
    console.log(`   Batch: ${fragment.batchNumber}`);
    console.log(`   Size: ${(data.length / 1024).toFixed(2)} KB`);
    console.log(`   Duration: ${fragment.duration}s`);

    // Echo back after delay (simulating processing)
    setTimeout(() => {
      socket.emit('fragment:processed', {
        fragment,
        data,
        metadata: {
          processingTime: ECHO_DELAY_MS,
          processor: 'echo-audio-processor',
          timestamp: new Date().toISOString(),
        }
      });

      stats.fragmentsEchoed++;
      stats.totalBytesEchoed += data.length;

      console.log(`[${new Date().toISOString()}] 📤 Echoed fragment: ${fragment.id}\n`);
    }, ECHO_DELAY_MS);
  });

  /**
   * Handle disconnection
   */
  socket.on('disconnect', () => {
    console.log(`[${new Date().toISOString()}] ❌ Client disconnected: ${socket.id}\n`);
  });

  /**
   * Handle errors
   */
  socket.on('error', (error) => {
    console.error(`[${new Date().toISOString()}] ⚠️  Socket error:`, error);
  });
});

/**
 * Print statistics every 30 seconds
 */
setInterval(() => {
  const uptime = Math.floor((Date.now() - stats.startTime.getTime()) / 1000);
  
  console.log(`\n📊 Statistics (uptime: ${uptime}s):`);
  console.log(`   Connections: ${stats.connections}`);
  console.log(`   Fragments received: ${stats.fragmentsReceived}`);
  console.log(`   Fragments echoed: ${stats.fragmentsEchoed}`);
  console.log(`   Data received: ${(stats.totalBytesReceived / 1024 / 1024).toFixed(2)} MB`);
  console.log(`   Data echoed: ${(stats.totalBytesEchoed / 1024 / 1024).toFixed(2)} MB\n`);
}, 30000);

/**
 * Graceful shutdown
 */
process.on('SIGINT', () => {
  console.log('\n\n🛑 Shutting down Echo Audio Processor...');
  io.close(() => {
    console.log('✅ Server closed\n');
    process.exit(0);
  });
});

console.log('✅ Echo Audio Processor ready!\n');

