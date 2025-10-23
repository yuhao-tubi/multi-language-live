#!/usr/bin/env node
/**
 * Detailed Test Subscriber for Mock Media Service
 * 
 * This script provides comprehensive logging and verification of the
 * mock-media-service WebSocket connection and fragment delivery.
 * 
 * Usage:
 *   node apps/mock-media-service/test-subscriber.js [streamId]
 * 
 * Example:
 *   node apps/mock-media-service/test-subscriber.js test-stream
 */

const { io } = require('socket.io-client');
const dotenv = require('dotenv');
const path = require('path');
const fs = require('fs');

// Load environment configuration
dotenv.config({ path: path.join(__dirname, '.env') });

// Configuration
const HOST = process.env.HOST || 'localhost';
const PORT = process.env.PORT || 4000;
const SERVER_URL = `ws://${HOST}:${PORT}`;
const STREAM_ID = process.argv[2] || process.env.STREAM_ID || 'test-stream';
const SAVE_FRAGMENTS = process.env.SAVE_FRAGMENTS === 'true';

// Metrics tracking
const metrics = {
  connectionStartTime: null,
  connectionEstablishedTime: null,
  subscriptionTime: null,
  firstFragmentTime: null,
  fragmentTimestamps: [],
  fragments: [],
  totalBytesReceived: 0,
  errors: [],
  disconnectTime: null
};

// Color codes for terminal output
const colors = {
  reset: '\x1b[0m',
  bright: '\x1b[1m',
  dim: '\x1b[2m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m',
  red: '\x1b[31m',
  magenta: '\x1b[35m'
};

function log(color, prefix, message, data = null) {
  const timestamp = new Date().toISOString();
  console.log(`${colors.dim}[${timestamp}]${colors.reset} ${color}${prefix}${colors.reset} ${message}`);
  if (data) {
    console.log(`${colors.dim}${JSON.stringify(data, null, 2)}${colors.reset}`);
  }
}

function logSection(title) {
  console.log('\n' + colors.bright + '='.repeat(70) + colors.reset);
  console.log(colors.bright + colors.cyan + title.toUpperCase() + colors.reset);
  console.log(colors.bright + '='.repeat(70) + colors.reset + '\n');
}

function logSubsection(title) {
  console.log(colors.yellow + '\n--- ' + title + ' ---' + colors.reset);
}

// Print initial configuration
logSection('Mock Media Service - Test Subscriber');
log(colors.blue, '[CONFIG]', 'Client Configuration:');
console.log(`  ${colors.cyan}Server URL:${colors.reset} ${SERVER_URL}`);
console.log(`  ${colors.cyan}Stream ID:${colors.reset} ${STREAM_ID}`);
console.log(`  ${colors.cyan}Save Fragments:${colors.reset} ${SAVE_FRAGMENTS}`);
console.log(`  ${colors.cyan}Expected Fragments:${colors.reset} ${process.env.MAX_FRAGMENTS_PER_STREAM || 4}`);

// Check .env file exists
const envPath = path.join(__dirname, '.env');
if (fs.existsSync(envPath)) {
  log(colors.green, '[CONFIG]', '.env file found and loaded', { path: envPath });
} else {
  log(colors.yellow, '[WARNING]', '.env file not found, using defaults', { path: envPath });
}

logSection('Connection Phase');

// Record connection start time
metrics.connectionStartTime = Date.now();
log(colors.blue, '[CONNECT]', 'Initiating connection to server...', {
  url: SERVER_URL,
  transport: 'websocket',
  reconnection: false
});

// Create Socket.IO client
const socket = io(SERVER_URL, {
  transports: ['websocket'],
  reconnection: false,
  timeout: 10000
});

// Connection successful
socket.on('connect', () => {
  metrics.connectionEstablishedTime = Date.now();
  const connectionTime = metrics.connectionEstablishedTime - metrics.connectionStartTime;
  
  logSection('Connection Established');
  log(colors.green, '[SUCCESS]', 'Connected to server', {
    socketId: socket.id,
    connectionTime: `${connectionTime}ms`,
    transport: socket.io.engine.transport.name
  });
  
  // Subscribe to stream
  logSubsection('Subscription Request');
  metrics.subscriptionTime = Date.now();
  log(colors.blue, '[SUBSCRIBE]', `Requesting subscription to stream: ${STREAM_ID}`);
  socket.emit('subscribe', { streamId: STREAM_ID });
});

// Subscription confirmed
socket.on('subscribed', (data) => {
  const subscriptionTime = Date.now() - metrics.subscriptionTime;
  
  logSubsection('Subscription Confirmed');
  log(colors.green, '[SUCCESS]', 'Successfully subscribed to stream', {
    streamId: data.streamId,
    subscriptionTime: `${subscriptionTime}ms`
  });
  
  log(colors.cyan, '[WAITING]', 'Waiting for fragments...');
});

// Fragment received
socket.on('fragment:data', (delivery) => {
  const { fragment, data } = delivery;
  const now = Date.now();
  
  if (!metrics.firstFragmentTime) {
    metrics.firstFragmentTime = now;
    const timeToFirstFragment = now - metrics.connectionEstablishedTime;
    logSection('Fragment Delivery Started');
    log(colors.magenta, '[TIMING]', 'Time to first fragment', { 
      milliseconds: timeToFirstFragment,
      seconds: (timeToFirstFragment / 1000).toFixed(2) 
    });
  }
  
  // Calculate interval from previous fragment
  const intervalFromPrevious = metrics.fragmentTimestamps.length > 0
    ? now - metrics.fragmentTimestamps[metrics.fragmentTimestamps.length - 1]
    : 0;
  
  metrics.fragmentTimestamps.push(now);
  metrics.fragments.push({
    id: fragment.id,
    sequenceNumber: fragment.sequenceNumber,
    size: data.length,
    timestamp: now
  });
  metrics.totalBytesReceived += data.length;
  
  // Log fragment details
  logSubsection(`Fragment ${fragment.sequenceNumber + 1}/${process.env.MAX_FRAGMENTS_PER_STREAM || 4}`);
  
  log(colors.green, '[RECEIVED]', 'Fragment data received', {
    id: fragment.id,
    sequenceNumber: fragment.sequenceNumber,
    streamId: fragment.streamId,
    size: {
      bytes: data.length.toLocaleString(),
      kilobytes: (data.length / 1024).toFixed(2),
      megabytes: (data.length / (1024 * 1024)).toFixed(4)
    },
    timing: {
      fragmentTimestamp: new Date(fragment.timestamp).toISOString(),
      receivedAt: new Date(now).toISOString(),
      intervalFromPrevious: intervalFromPrevious > 0 ? `${intervalFromPrevious}ms` : 'N/A (first fragment)'
    },
    audio: {
      codec: fragment.codec,
      sampleRate: `${fragment.sampleRate} Hz`,
      channels: fragment.channels,
      bitrate: `${fragment.bitrate / 1000} kbps`,
      duration: `${fragment.duration}ms`
    }
  });
  
  if (fragment.metadata) {
    log(colors.dim, '[METADATA]', 'Fragment metadata', fragment.metadata);
  }
  
  // Validate data buffer
  if (Buffer.isBuffer(data)) {
    log(colors.green, '[VALIDATE]', 'Data validation passed: Buffer type confirmed');
    
    // Check for m4s signature (ftyp box)
    if (data.length >= 8) {
      const boxType = data.slice(4, 8).toString('ascii');
      log(colors.cyan, '[M4S]', `First box type: ${boxType}`, {
        firstBytes: data.slice(0, 16).toString('hex')
      });
    }
  } else {
    log(colors.red, '[ERROR]', 'Data validation failed: Not a Buffer', { type: typeof data });
    metrics.errors.push('Invalid data type received');
  }
  
  // Save fragment to disk if enabled
  if (SAVE_FRAGMENTS) {
    const outputDir = path.join(__dirname, 'output');
    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }
    const filename = `${fragment.streamId}-${fragment.sequenceNumber}.m4s`;
    const filepath = path.join(outputDir, filename);
    fs.writeFileSync(filepath, data);
    log(colors.cyan, '[SAVED]', `Fragment saved to disk: ${filename}`);
  }
  
  // Send acknowledgment
  const ackSendTime = Date.now();
  socket.emit('fragment:ack', { fragmentId: fragment.id });
  log(colors.blue, '[ACK]', 'Acknowledgment sent', {
    fragmentId: fragment.id,
    ackLatency: `${Date.now() - ackSendTime}ms`
  });
});

// Stream complete
socket.on('stream:complete', (data) => {
  logSection('Stream Completed');
  
  const totalTime = Date.now() - metrics.connectionEstablishedTime;
  const avgInterval = metrics.fragmentTimestamps.length > 1
    ? (metrics.fragmentTimestamps[metrics.fragmentTimestamps.length - 1] - metrics.fragmentTimestamps[0]) / (metrics.fragmentTimestamps.length - 1)
    : 0;
  
  log(colors.green, '[COMPLETE]', 'Stream completed successfully', {
    streamId: data.streamId,
    totalFragments: metrics.fragments.length,
    totalTime: `${totalTime}ms (${(totalTime / 1000).toFixed(2)}s)`,
    totalBytesReceived: metrics.totalBytesReceived.toLocaleString(),
    totalMegabytes: (metrics.totalBytesReceived / (1024 * 1024)).toFixed(2),
    averageFragmentInterval: `${avgInterval.toFixed(0)}ms`,
    expectedInterval: `${process.env.FRAGMENT_DATA_INTERVAL || 15000}ms`
  });
  
  // Calculate interval statistics
  if (metrics.fragmentTimestamps.length > 1) {
    logSubsection('Fragment Interval Analysis');
    const intervals = [];
    for (let i = 1; i < metrics.fragmentTimestamps.length; i++) {
      const interval = metrics.fragmentTimestamps[i] - metrics.fragmentTimestamps[i - 1];
      intervals.push(interval);
      console.log(`  Fragment ${i - 1} → ${i}: ${colors.cyan}${interval}ms${colors.reset}`);
    }
    
    const minInterval = Math.min(...intervals);
    const maxInterval = Math.max(...intervals);
    const avgIntervalCalc = intervals.reduce((a, b) => a + b, 0) / intervals.length;
    
    console.log(`\n  ${colors.yellow}Statistics:${colors.reset}`);
    console.log(`    Min interval: ${minInterval}ms`);
    console.log(`    Max interval: ${maxInterval}ms`);
    console.log(`    Avg interval: ${avgIntervalCalc.toFixed(2)}ms`);
    console.log(`    Std deviation: ${calculateStdDev(intervals).toFixed(2)}ms`);
  }
  
  log(colors.yellow, '[INFO]', 'Server will disconnect socket shortly...');
});

// Unsubscribed
socket.on('unsubscribed', (data) => {
  log(colors.yellow, '[UNSUBSCRIBED]', 'Unsubscribed from stream', { streamId: data.streamId });
});

// Error occurred
socket.on('error', (error) => {
  logSection('Error Occurred');
  log(colors.red, '[ERROR]', 'Socket error received', error);
  metrics.errors.push(error);
  
  if (error.availableStreams) {
    log(colors.cyan, '[INFO]', 'Available streams on server', { 
      streams: error.availableStreams 
    });
  }
});

// Disconnected
socket.on('disconnect', (reason) => {
  metrics.disconnectTime = Date.now();
  
  logSection('Disconnected');
  log(colors.yellow, '[DISCONNECT]', 'Disconnected from server', {
    reason: reason,
    totalConnectionTime: `${metrics.disconnectTime - metrics.connectionEstablishedTime}ms`
  });
  
  printFinalSummary();
  process.exit(0);
});

// Connection error
socket.on('connect_error', (error) => {
  logSection('Connection Error');
  log(colors.red, '[ERROR]', 'Failed to connect to server', {
    error: error.message,
    serverUrl: SERVER_URL
  });
  
  console.log('\n' + colors.yellow + 'Troubleshooting Steps:' + colors.reset);
  console.log('  1. Check if mock-media-service is running:');
  console.log(`     ${colors.dim}npx nx serve mock-media-service${colors.reset}`);
  console.log('  2. Verify server URL and port in .env file');
  console.log(`     ${colors.dim}Expected: ws://${HOST}:${PORT}${colors.reset}`);
  console.log('  3. Test HTTP endpoint:');
  console.log(`     ${colors.dim}curl http://${HOST}:${PORT}/${colors.reset}`);
  console.log('  4. Check firewall/network settings\n');
  
  printFinalSummary();
  process.exit(1);
});

// Graceful shutdown
process.on('SIGINT', () => {
  logSection('Shutdown Requested');
  log(colors.yellow, '[SHUTDOWN]', 'Received SIGINT, shutting down gracefully...');
  socket.disconnect();
  printFinalSummary();
  process.exit(0);
});

// Helper function to calculate standard deviation
function calculateStdDev(values) {
  const avg = values.reduce((a, b) => a + b, 0) / values.length;
  const squareDiffs = values.map(value => Math.pow(value - avg, 2));
  const avgSquareDiff = squareDiffs.reduce((a, b) => a + b, 0) / squareDiffs.length;
  return Math.sqrt(avgSquareDiff);
}

// Print final summary
function printFinalSummary() {
  logSection('Test Summary');
  
  console.log(colors.bright + 'Connection Metrics:' + colors.reset);
  console.log(`  Connection time: ${metrics.connectionEstablishedTime ? metrics.connectionEstablishedTime - metrics.connectionStartTime : 'N/A'}ms`);
  console.log(`  Time to first fragment: ${metrics.firstFragmentTime ? metrics.firstFragmentTime - metrics.connectionEstablishedTime : 'N/A'}ms`);
  console.log(`  Total fragments received: ${colors.cyan}${metrics.fragments.length}${colors.reset}`);
  console.log(`  Total bytes received: ${colors.cyan}${metrics.totalBytesReceived.toLocaleString()}${colors.reset} (${(metrics.totalBytesReceived / (1024 * 1024)).toFixed(2)} MB)`);
  console.log(`  Errors encountered: ${metrics.errors.length > 0 ? colors.red : colors.green}${metrics.errors.length}${colors.reset}`);
  
  if (metrics.errors.length > 0) {
    console.log('\n' + colors.red + 'Errors:' + colors.reset);
    metrics.errors.forEach((err, idx) => {
      console.log(`  ${idx + 1}. ${JSON.stringify(err)}`);
    });
  }
  
  console.log('\n' + colors.bright + 'Fragment Details:' + colors.reset);
  if (metrics.fragments.length > 0) {
    metrics.fragments.forEach(frag => {
      console.log(`  ${colors.cyan}${frag.id}${colors.reset}: ${frag.size.toLocaleString()} bytes`);
    });
  } else {
    console.log(`  ${colors.yellow}No fragments received${colors.reset}`);
  }
  
  console.log('\n' + colors.bright + '='.repeat(70) + colors.reset);
  console.log(colors.bright + colors.green + 'TEST COMPLETED' + colors.reset);
  console.log(colors.bright + '='.repeat(70) + colors.reset + '\n');
}

