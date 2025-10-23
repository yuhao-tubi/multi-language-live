/**
 * Example Socket.IO Client for Mock Media Service
 * 
 * Usage:
 *   1. Start the mock-media-service: npx nx serve mock-media-service
 *   2. Ensure you have a stream with m4s files in: src/assets/audio-fragments/test-stream/
 *   3. Install socket.io-client: npm install socket.io-client
 *   4. Run this script: node apps/mock-media-service/example-client.js
 */

const { io } = require('socket.io-client');
const dotenv = require('dotenv');
const path = require('path');

// Load environment configuration from .env file
dotenv.config({ path: path.join(__dirname, '.env') });

// Configuration from .env
const HOST = process.env.HOST || 'localhost';
const PORT = process.env.PORT || 4000;
const SERVER_URL = `ws://${HOST}:${PORT}`;
const STREAM_ID = process.env.STREAM_ID || 'test-stream'; // Change this to match your stream directory name

console.log('='.repeat(60));
console.log('Mock Media Service - Example Client');
console.log('='.repeat(60));
console.log(`Connecting to: ${SERVER_URL}`);
console.log(`Stream ID: ${STREAM_ID}`);
console.log('='.repeat(60));

// Connect to the server
const socket = io(SERVER_URL, {
  transports: ['websocket'],
  reconnection: false
});

let fragmentCount = 0;

socket.on('connect', () => {
  console.log('\n✓ Connected to server');
  console.log(`  Socket ID: ${socket.id}`);
  
  // Subscribe to a stream
  console.log(`\n→ Subscribing to stream: ${STREAM_ID}`);
  socket.emit('subscribe', { streamId: STREAM_ID });
});

socket.on('subscribed', (data) => {
  console.log(`\n✓ Successfully subscribed to stream: ${data.streamId}`);
  console.log('  Waiting for fragments...\n');
});

socket.on('fragment:data', (delivery) => {
  const { fragment, data } = delivery;
  fragmentCount++;
  
  console.log(`📦 Fragment ${fragmentCount}/4 Received:`);
  console.log(`  ID: ${fragment.id}`);
  console.log(`  Sequence: ${fragment.sequenceNumber}`);
  console.log(`  Size: ${data.length.toLocaleString()} bytes (${(data.length / 1024).toFixed(2)} KB)`);
  console.log(`  Codec: ${fragment.codec}`);
  console.log(`  Sample Rate: ${fragment.sampleRate} Hz`);
  console.log(`  Channels: ${fragment.channels}`);
  console.log(`  Bitrate: ${fragment.bitrate / 1000} kbps`);
  console.log(`  Duration: ${fragment.duration}ms`);
  
  if (fragment.metadata) {
    console.log(`  File: ${fragment.metadata.fileName}`);
  }
  
  // Acknowledge receipt
  socket.emit('fragment:ack', { fragmentId: fragment.id });
  console.log(`  ✓ Acknowledged\n`);
});

socket.on('stream:complete', (data) => {
  console.log('='.repeat(60));
  console.log(`✓ Stream completed: ${data.streamId}`);
  console.log(`  Total fragments received: ${fragmentCount}`);
  console.log('  Server will disconnect socket...');
  console.log('='.repeat(60));
});

socket.on('unsubscribed', (data) => {
  console.log(`\n✓ Unsubscribed from stream: ${data.streamId}`);
});

socket.on('error', (error) => {
  console.error('\n✗ Error:', error);
  if (error.availableStreams) {
    console.log('\n  Available streams:', error.availableStreams);
  }
});

socket.on('disconnect', (reason) => {
  console.log(`\n✓ Disconnected: ${reason}\n`);
  process.exit(0);
});

socket.on('connect_error', (error) => {
  console.error('\n✗ Connection error:', error.message);
  console.log('\nTroubleshooting:');
  console.log('  1. Is the mock-media-service running?');
  console.log('  2. Check the server URL and port (default: ws://localhost:4000)');
  console.log('  3. Verify no firewall is blocking the connection\n');
  process.exit(1);
});

// Handle graceful shutdown
process.on('SIGINT', () => {
  console.log('\n\nShutting down client...');
  socket.disconnect();
  process.exit(0);
});

