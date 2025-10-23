import express from 'express';
import { createServer } from 'http';
import { Server } from 'socket.io';
import * as dotenv from 'dotenv';
import * as path from 'path';
import { FragmentProvider } from './services/fragment-provider.service';
import { StreamManager } from './services/stream-manager.service';
import { setupSocketHandlers } from './handlers/socket.handler';

// Load environment variables
dotenv.config({ path: path.join(__dirname, '../.env') });

// Configuration
const host = process.env.HOST ?? 'localhost';
const port = process.env.PORT ? Number(process.env.PORT) : 4000;
const fragmentDataInterval = process.env.FRAGMENT_DATA_INTERVAL 
  ? Number(process.env.FRAGMENT_DATA_INTERVAL) 
  : 15000;
const ackTimeoutMs = process.env.ACK_TIMEOUT_MS 
  ? Number(process.env.ACK_TIMEOUT_MS) 
  : 5000;
const maxRetries = process.env.MAX_RETRIES 
  ? Number(process.env.MAX_RETRIES) 
  : 3;
const maxFragmentsPerStream = process.env.MAX_FRAGMENTS_PER_STREAM 
  ? Number(process.env.MAX_FRAGMENTS_PER_STREAM) 
  : 4;

console.log('Mock Media Service Configuration:');
console.log(`  Host: ${host}`);
console.log(`  Port: ${port}`);
console.log(`  Fragment Data Interval: ${fragmentDataInterval}ms`);
console.log(`  ACK Timeout: ${ackTimeoutMs}ms`);
console.log(`  Max Retries: ${maxRetries}`);
console.log(`  Max Fragments Per Stream: ${maxFragmentsPerStream}`);

// Create Express app for health checks
const app = express();
app.use(express.json());

// Create HTTP server
const httpServer = createServer(app);

// Create Socket.IO server
const io = new Server(httpServer, {
  cors: {
    origin: '*',
    methods: ['GET', 'POST']
  },
  maxHttpBufferSize: 10e6 // 10MB for large audio fragments
});

// Initialize services
// Resolve assets path - always use source directory unless ASSETS_PATH is explicitly set
// Use process.cwd() which gives us the workspace root when running with nx serve
const workspaceRoot = process.cwd();
const fragmentsPath = process.env.ASSETS_PATH 
  ? path.resolve(process.env.ASSETS_PATH)
  : path.join(workspaceRoot, 'apps', 'mock-media-service', 'src', 'assets', 'audio-fragments');

const fragmentProvider = new FragmentProvider(
  fragmentsPath,
  fragmentDataInterval,
  maxFragmentsPerStream
);

const streamManager = new StreamManager(
  io,
  fragmentProvider,
  ackTimeoutMs,
  maxRetries
);

// Health check endpoint
app.get('/', (req, res) => {
  res.json({ 
    message: 'Mock Media Service',
    status: 'running',
    stats: streamManager.getStats()
  });
});

// Available streams endpoint
app.get('/streams', async (req, res) => {
  try {
    const streams = await fragmentProvider.getAvailableStreams();
    res.json({ streams });
  } catch (error) {
    res.status(500).json({ 
      error: 'Failed to fetch streams',
      message: error instanceof Error ? error.message : String(error)
    });
  }
});

// Socket.IO connection handler
io.on('connection', (socket) => {
  setupSocketHandlers(socket, streamManager);
});

// Start server
httpServer.listen(port, host, () => {
  console.log(`\n[ ready ] Mock Media Service`);
  console.log(`  HTTP: http://${host}:${port}`);
  console.log(`  WebSocket: ws://${host}:${port}`);
  console.log(`  Fragments path: ${fragmentsPath}\n`);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('SIGTERM received, shutting down gracefully...');
  httpServer.close(() => {
    console.log('Server closed');
    process.exit(0);
  });
});

process.on('SIGINT', () => {
  console.log('\nSIGINT received, shutting down gracefully...');
  httpServer.close(() => {
    console.log('Server closed');
    process.exit(0);
  });
});
