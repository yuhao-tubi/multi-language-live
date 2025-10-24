/**
 * Manual Test: StreamPublisher Playback Test
 * 
 * This test reads pre-recorded batch files and publishes them to SRS
 * at the correct pace (30 seconds per clip) to simulate real-time streaming.
 * 
 * Usage:
 *   npm run test:stream-publisher
 *   or
 *   npx tsx tests/manual/stream-publisher-playback.test.ts
 * 
 * Prerequisites:
 *   - SRS server running on rtmp://localhost/live
 *   - Batch files in storage/processed_fragments/output/test-stream/
 */

import { StreamPublisher } from '../../src/modules/StreamPublisher.js';
import { RemuxedOutput } from '../../src/types/index.js';
import path from 'path';
import fs from 'fs-extra';
import { fileURLToPath } from 'url';

// ESM dirname workaround
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Configuration
const CONFIG = {
  streamId: 'test-stream',
  srsRtmpUrl: 'rtmp://localhost/live',
  batchDirectory: path.join(__dirname, '../../storage/processed_fragments/output/test-stream'),
  fragmentDurationSeconds: 30, // Each batch is ~30 seconds
  maxReconnectAttempts: 3,
  reconnectDelayMs: 2000,
  // Sliding window cleanup (keep last 3 segments + 2 safety buffer = 5 total)
  maxSegmentsToKeep: 3,
  enableCleanup: true,
  cleanupSafetyBuffer: 2,
};

/**
 * Sleep utility
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Format duration for display
 */
function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Get all batch files in order
 */
async function getBatchFiles(): Promise<Array<{ batchNumber: number; path: string; size: number }>> {
  const files = await fs.readdir(CONFIG.batchDirectory);
  
  const batchFiles = files
    .filter((file) => file.startsWith('batch-') && file.endsWith('.mp4'))
    .map((file) => {
      const match = file.match(/batch-(\d+)\.mp4/);
      if (!match) return null;
      
      const batchNumber = parseInt(match[1], 10);
      const filePath = path.join(CONFIG.batchDirectory, file);
      
      return { batchNumber, path: filePath };
    })
    .filter((item): item is { batchNumber: number; path: string } => item !== null)
    .sort((a, b) => a.batchNumber - b.batchNumber);

  // Get file sizes
  const batchFilesWithSize = await Promise.all(
    batchFiles.map(async (file) => {
      const stats = await fs.stat(file.path);
      return { ...file, size: stats.size };
    })
  );

  return batchFilesWithSize;
}

/**
 * Main test runner
 */
async function runTest() {
  console.log('🎬 StreamPublisher Playback Test');
  console.log('================================\n');

  // Check if batch directory exists
  if (!(await fs.pathExists(CONFIG.batchDirectory))) {
    console.error(`❌ Batch directory not found: ${CONFIG.batchDirectory}`);
    console.error('Please ensure batch files exist before running this test.');
    process.exit(1);
  }

  // Get batch files
  const batchFiles = await getBatchFiles();
  
  if (batchFiles.length === 0) {
    console.error('❌ No batch files found in directory');
    process.exit(1);
  }

  console.log(`📁 Found ${batchFiles.length} batch files:`);
  batchFiles.forEach((file) => {
    const sizeMB = (file.size / 1024 / 1024).toFixed(2);
    console.log(`   - batch-${file.batchNumber}.mp4 (${sizeMB} MB)`);
  });
  console.log();

  // Calculate total duration
  const totalDurationSeconds = batchFiles.length * CONFIG.fragmentDurationSeconds;
  console.log(`⏱️  Total stream duration: ${formatDuration(totalDurationSeconds)} (${totalDurationSeconds}s)`);
  console.log(`🎯 Publishing rate: ${CONFIG.fragmentDurationSeconds}s per fragment\n`);

  // Create StreamPublisher instance
  console.log('🔧 Initializing StreamPublisher...');
  const publisher = new StreamPublisher({
    streamId: CONFIG.streamId,
    srsRtmpUrl: CONFIG.srsRtmpUrl,
    outputDirectory: CONFIG.batchDirectory,
    maxReconnectAttempts: CONFIG.maxReconnectAttempts,
    reconnectDelayMs: CONFIG.reconnectDelayMs,
    maxSegmentsToKeep: CONFIG.maxSegmentsToKeep,
    enableCleanup: CONFIG.enableCleanup,
    cleanupSafetyBuffer: CONFIG.cleanupSafetyBuffer,
  });

  // Set up event handlers
  let publishedCount = 0;
  let errorOccurred = false;

  publisher.on('started', () => {
    console.log('✅ Publisher started successfully\n');
  });

  publisher.on('fragment:published', (batchNumber) => {
    publishedCount++;
    const progress = ((publishedCount / batchFiles.length) * 100).toFixed(1);
    console.log(`📡 Fragment ${batchNumber} published (${publishedCount}/${batchFiles.length} - ${progress}%)`);
  });

  publisher.on('reconnecting', (attempt) => {
    console.log(`🔄 Reconnecting... (attempt ${attempt}/${CONFIG.maxReconnectAttempts})`);
  });

  publisher.on('reconnected', () => {
    console.log('✅ Reconnected successfully');
  });

  publisher.on('error', (error) => {
    console.error('❌ Publisher error:', error.message);
    errorOccurred = true;
  });

  publisher.on('stopped', () => {
    console.log('\n🛑 Publisher stopped');
  });

  // Handle graceful shutdown
  let isShuttingDown = false;
  
  const shutdown = async () => {
    if (isShuttingDown) return;
    isShuttingDown = true;
    
    console.log('\n\n🛑 Shutdown signal received, stopping publisher...');
    try {
      await publisher.stop();
      console.log('✅ Publisher stopped gracefully');
    } catch (error) {
      console.error('❌ Error during shutdown:', error);
    }
    process.exit(errorOccurred ? 1 : 0);
  };

  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);

  try {
    // Start the publisher
    console.log('🚀 Starting publisher...');
    await publisher.start();

    // Give FFmpeg a moment to stabilize
    await sleep(1000);

    console.log('\n📺 Stream URL: ' + `rtmp://localhost/live/${CONFIG.streamId}`);
    console.log('💡 You can watch with: ffplay rtmp://localhost/live/' + CONFIG.streamId);
    console.log('💡 Or with VLC: Open Network Stream -> rtmp://localhost/live/' + CONFIG.streamId);
    console.log('\n🎬 Starting playback...\n');

    // Publish each batch file at the correct pace
    const startTime = Date.now();
    
    for (let i = 0; i < batchFiles.length; i++) {
      const batchFile = batchFiles[i];
      const elapsedSeconds = Math.floor((Date.now() - startTime) / 1000);
      
      console.log(`\n[${formatDuration(elapsedSeconds)}] Publishing batch ${batchFile.batchNumber}...`);
      
      // Create RemuxedOutput object
      const remuxedOutput: RemuxedOutput = {
        batchNumber: batchFile.batchNumber,
        outputPath: batchFile.path,
        size: batchFile.size,
        timestamp: new Date(),
      };

      // Publish the fragment
      try {
        await publisher.publishFragment(remuxedOutput);
        
        // Wait for fragment duration before publishing next (except for last fragment)
        if (i < batchFiles.length - 1) {
          console.log(`⏳ Waiting ${CONFIG.fragmentDurationSeconds}s before next fragment...`);
          await sleep(CONFIG.fragmentDurationSeconds * 1000);
        }
      } catch (error) {
        console.error(`❌ Failed to publish batch ${batchFile.batchNumber}:`, error);
        errorOccurred = true;
        break;
      }

      // Check if we should stop due to errors
      if (errorOccurred) {
        console.error('\n❌ Stopping due to errors');
        break;
      }
    }

    // Final summary
    const totalElapsedSeconds = Math.floor((Date.now() - startTime) / 1000);
    console.log('\n\n═══════════════════════════════════');
    console.log('📊 Playback Complete');
    console.log('═══════════════════════════════════');
    console.log(`✅ Published: ${publishedCount}/${batchFiles.length} fragments`);
    console.log(`⏱️  Total time: ${formatDuration(totalElapsedSeconds)}`);
    console.log(`📡 Stream: rtmp://localhost/live/${CONFIG.streamId}`);
    
    if (errorOccurred) {
      console.log('⚠️  Some errors occurred during playback');
    }
    
    console.log('\n💡 Keeping publisher running for 10 more seconds...');
    console.log('   (This allows viewers to catch up with the stream)\n');
    await sleep(10000);

    // Stop the publisher
    console.log('🛑 Stopping publisher...');
    await publisher.stop();
    
    console.log('\n✅ Test completed successfully!');
    process.exit(errorOccurred ? 1 : 0);

  } catch (error) {
    console.error('\n❌ Test failed:', error);
    
    // Try to stop publisher
    try {
      await publisher.stop();
    } catch (stopError) {
      console.error('Error stopping publisher:', stopError);
    }
    
    process.exit(1);
  }
}

// Run the test
runTest().catch((error) => {
  console.error('Unhandled error:', error);
  process.exit(1);
});

