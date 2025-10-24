/**
 * Fragment Chunker Module
 * Splits large remuxed fragments into smaller chunks for smooth stdin streaming
 */
import { createReadStream } from 'fs';
import { Writable } from 'stream';
import { EventEmitter } from 'events';
import fs from 'fs-extra';
import { getLogger } from '../utils/logger.js';

let logger: ReturnType<typeof getLogger> | null = null;

/**
 * FragmentChunker configuration
 */
export interface FragmentChunkerConfig {
  /** Chunk size in bytes (default: 256KB) */
  chunkSize?: number;
  /** Rate limit in bytes per second (0 = no limit, default: 0) */
  rateLimitBps?: number;
  /** Enable high water mark for backpressure (default: 16KB) */
  highWaterMark?: number;
}

/**
 * FragmentChunker events
 */
export interface FragmentChunkerEvents {
  'chunk:sent': (chunkNumber: number, size: number) => void;
  'fragment:complete': (totalChunks: number, totalBytes: number) => void;
  'error': (error: Error) => void;
}

/**
 * FragmentChunker module
 * Streams fragments in smaller chunks to avoid overwhelming stdin buffer
 */
export class FragmentChunker extends EventEmitter {
  private chunkSize: number;
  private rateLimitBps: number;
  private streamingQueue: Array<() => Promise<void>> = [];
  private isProcessingQueue: boolean = false;

  constructor(config: FragmentChunkerConfig = {}) {
    super();
    this.chunkSize = config.chunkSize ?? 1 * 1024 * 1024; // 1MB default
    this.rateLimitBps = config.rateLimitBps ?? 0; // No rate limiting by default

    // Lazy initialize logger
    if (!logger) {
      try {
        logger = getLogger().child({ context: 'FragmentChunker' });
      } catch {
        logger = null;
      }
    }

    this.log('info', `FragmentChunker initialized (chunk size: ${this.formatBytes(this.chunkSize)})`);
    if (this.rateLimitBps > 0) {
      this.log('info', `Rate limiting enabled: ${this.formatBytes(this.rateLimitBps)}/s`);
    }
  }

  private log(level: 'debug' | 'info' | 'warn' | 'error', message: string, ...args: unknown[]): void {
    if (logger) {
      logger[level](message, ...args);
    }
  }

  private formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)}MB`;
  }

  /**
   * Stream a fragment to stdin in chunks
   * @param fragmentPath Path to the fragment file
   * @param stdinStream Writable stream (FFmpeg stdin)
   * @param batchNumber Batch number for logging
   */
  async streamFragment(
    fragmentPath: string,
    stdinStream: Writable,
    batchNumber: number
  ): Promise<void> {
    // Log when new remuxed batch is received
    this.log('info', `🆕 New remuxed batch received: batch-${batchNumber}`);
    this.log('info', `   Fragment path: ${fragmentPath}`);
    this.log('info', `   Current queue length: ${this.streamingQueue.length}`);
    this.log('info', `   Queue processing: ${this.isProcessingQueue ? 'ACTIVE' : 'IDLE'}`);
    
    // Add to queue and process
    return new Promise<void>((resolve, reject) => {
      this.streamingQueue.push(async () => {
        try {
          this.log('info', `🎬 Starting to process batch-${batchNumber} from queue`);
          await this.doStreamFragment(fragmentPath, stdinStream, batchNumber);
          this.log('info', `✅ Completed processing batch-${batchNumber}`);
          resolve();
        } catch (error) {
          this.log('error', `❌ Failed to process batch-${batchNumber}:`, error);
          reject(error);
        }
      });

      this.log('info', `   Batch-${batchNumber} added to queue (new queue length: ${this.streamingQueue.length})`);

      // Start processing queue if not already processing
      if (!this.isProcessingQueue) {
        this.log('info', `🚀 Starting queue processor...`);
        this.processQueue().catch((error) => {
          this.log('error', 'Queue processing error:', error);
        });
      }
    });
  }

  /**
   * Process the streaming queue sequentially
   */
  private async processQueue(): Promise<void> {
    if (this.isProcessingQueue) {
      this.log('debug', '⏩ Queue processor already running, skipping...');
      return;
    }

    this.isProcessingQueue = true;
    this.log('info', `🔄 Queue processor started (${this.streamingQueue.length} tasks pending)`);

    let taskNumber = 0;
    while (this.streamingQueue.length > 0) {
      taskNumber++;
      const remainingTasks = this.streamingQueue.length;
      this.log('info', `📋 Processing task ${taskNumber} (${remainingTasks} remaining in queue)`);
      
      const task = this.streamingQueue.shift();
      if (task) {
        try {
          await task();
          this.log('info', `✓ Task ${taskNumber} completed successfully`);
        } catch (error) {
          this.log('error', `✗ Task ${taskNumber} execution error:`, error);
          // Continue processing queue even if one task fails
        }
      }
    }

    this.isProcessingQueue = false;
    this.log('info', `🏁 Queue processor finished (processed ${taskNumber} tasks)`);
  }

  /**
   * Actually stream a fragment to stdin in chunks
   * @param fragmentPath Path to the fragment file
   * @param stdinStream Writable stream (FFmpeg stdin)
   * @param batchNumber Batch number for logging
   */
  private async doStreamFragment(
    fragmentPath: string,
    stdinStream: Writable,
    batchNumber: number
  ): Promise<void> {
    // Verify fragment exists
    if (!(await fs.pathExists(fragmentPath))) {
      throw new Error(`Fragment file does not exist: ${fragmentPath}`);
    }

    const fragmentStats = await fs.stat(fragmentPath);
    const totalSize = fragmentStats.size;
    const estimatedChunks = Math.ceil(totalSize / this.chunkSize);

    this.log('info', `📦 Streaming fragment ${batchNumber} to stdin:`);
    this.log('info', `  Total size: ${this.formatBytes(totalSize)}`);
    this.log('info', `  Chunk size: ${this.formatBytes(this.chunkSize)}`);
    this.log('info', `  Est. chunks: ${estimatedChunks}`);
    this.log('info', `  Stdin writable: ${stdinStream.writable}`);
    this.log('info', `  Stdin destroyed: ${stdinStream.destroyed}`);

    return new Promise<void>((resolve, reject) => {
      let chunkNumber = 0;
      let bytesWritten = 0;
      let lastChunkTime = Date.now();
      let processingChunk = false;

      // Create read stream with controlled chunk size
      const readStream = createReadStream(fragmentPath, {
        highWaterMark: this.chunkSize,
      });

      // Handle chunk writing asynchronously
      const processChunk = async (chunk: Buffer) => {
        if (processingChunk) {
          this.log('warn', `  ⚠️ Chunk processing already in progress, skipping...`);
          return;
        }
        processingChunk = true;

        chunkNumber++;
        const chunkSize = chunk.length;
        const chunkStartTime = Date.now();

        this.log('info', `  ⬆️  Chunk ${chunkNumber}/${estimatedChunks} - Preparing to write ${this.formatBytes(chunkSize)} to stdin`);

        try {
          // Pause read stream to handle backpressure
          readStream.pause();
          this.log('debug', `  ⏸️  Read stream paused for chunk ${chunkNumber}`);

          // Apply rate limiting if enabled
          if (this.rateLimitBps > 0) {
            this.log('debug', `  ⏱️  Applying rate limit for chunk ${chunkNumber}...`);
            await this.applyRateLimit(chunkSize, lastChunkTime);
            lastChunkTime = Date.now();
          }

          // Check stdin state before writing
          this.log('debug', `  📊 Stdin state before write: writable=${stdinStream.writable}, destroyed=${stdinStream.destroyed}`);

          // Abort if stdin is no longer writable or destroyed
          if (!stdinStream.writable || stdinStream.destroyed) {
            const error = new Error(`stdin is not writable (destroyed=${stdinStream.destroyed})`);
            this.log('error', `  ❌ Cannot write chunk ${chunkNumber}: stdin unavailable`);
            throw error;
          }

          // Write chunk to stdin with backpressure handling
          this.log('info', `  ✍️  Writing chunk ${chunkNumber} to stdin (${this.formatBytes(chunkSize)})...`);
          const canWrite = stdinStream.write(chunk);
          const writeTime = Date.now() - chunkStartTime;

          if (!canWrite) {
            // Wait for drain event before continuing (with timeout and error handling)
            this.log('warn', `  🚰 Chunk ${chunkNumber}: backpressure detected (write returned false), waiting for drain...`);
            const drainStartTime = Date.now();
            
            try {
              await Promise.race([
                // Wait for drain event
                new Promise<void>((resolveDrain, rejectDrain) => {
                  const onDrain = () => {
                    cleanup();
                    const drainTime = Date.now() - drainStartTime;
                    this.log('info', `  ✅ Chunk ${chunkNumber}: drain complete (waited ${drainTime}ms)`);
                    resolveDrain();
                  };
                  
                  const onError = (err: Error) => {
                    cleanup();
                    this.log('error', `  ❌ Chunk ${chunkNumber}: stdin error during drain wait:`, err);
                    rejectDrain(err);
                  };
                  
                  const onClose = () => {
                    cleanup();
                    const err = new Error('stdin closed while waiting for drain');
                    this.log('error', `  ❌ Chunk ${chunkNumber}: stdin closed during drain wait`);
                    rejectDrain(err);
                  };
                  
                  const cleanup = () => {
                    stdinStream.removeListener('drain', onDrain);
                    stdinStream.removeListener('error', onError);
                    stdinStream.removeListener('close', onClose);
                  };
                  
                  stdinStream.once('drain', onDrain);
                  stdinStream.once('error', onError);
                  stdinStream.once('close', onClose);
                }),
                // Timeout after 30 seconds
                new Promise<never>((_, reject) => {
                  setTimeout(() => {
                    reject(new Error(`Drain timeout after 30s for chunk ${chunkNumber}`));
                  }, 30000);
                })
              ]);
            } catch (error) {
              this.log('error', `  ❌ Chunk ${chunkNumber}: drain wait failed:`, error);
              throw error;
            }
          } else {
            this.log('debug', `  ✅ Chunk ${chunkNumber}: write succeeded immediately (${writeTime}ms)`);
          }

          bytesWritten += chunkSize;
          const progress = ((bytesWritten / totalSize) * 100).toFixed(1);
          const totalTime = Date.now() - chunkStartTime;

          this.log('info', `  ✓ Chunk ${chunkNumber}/${estimatedChunks}: ${this.formatBytes(chunkSize)} written in ${totalTime}ms (${progress}% of batch-${batchNumber} complete)`);
          this.emit('chunk:sent', chunkNumber, chunkSize);

          // Resume reading next chunk
          processingChunk = false;
          readStream.resume();
          this.log('debug', `  ▶️  Read stream resumed after chunk ${chunkNumber}`);
        } catch (error) {
          const err = error as NodeJS.ErrnoException;
          this.log('error', `❌ Error writing chunk ${chunkNumber} to stdin:`, error);
          
          // EPIPE means the receiving end (FFmpeg) is gone - this is expected during reconnection
          if (err.code === 'EPIPE') {
            this.log('warn', `  Broken pipe detected - FFmpeg stdin closed (likely process died or reconnecting)`);
          }
          
          readStream.destroy();
          processingChunk = false;
          reject(error);
        }
      };

      readStream.on('data', (chunk: string | Buffer) => {
        // Ensure chunk is a Buffer
        const bufferChunk = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
        this.log('debug', `  📥 Read stream emitted data event: ${this.formatBytes(bufferChunk.length)}`);
        processChunk(bufferChunk).catch((error) => {
          this.log('error', '❌ Chunk processing error:', error);
          readStream.destroy();
          reject(error);
        });
      });

      readStream.on('end', () => {
        const avgChunkSize = bytesWritten / chunkNumber;
        this.log('info', `🎉 Fragment ${batchNumber} streaming complete!`);
        this.log('info', `   Total chunks sent: ${chunkNumber}`);
        this.log('info', `   Total bytes written to stdin: ${this.formatBytes(bytesWritten)}`);
        this.log('info', `   Average chunk size: ${this.formatBytes(avgChunkSize)}`);
        this.emit('fragment:complete', chunkNumber, bytesWritten);
        resolve();
      });

      readStream.on('error', (error) => {
        this.log('error', `❌ Read stream error for batch-${batchNumber}:`, error);
        this.log('error', `   Chunks processed before error: ${chunkNumber}`);
        this.log('error', `   Bytes written before error: ${this.formatBytes(bytesWritten)}`);
        this.emit('error', error);
        reject(error);
      });
    });
  }

  /**
   * Apply rate limiting by delaying if needed
   */
  private async applyRateLimit(chunkSize: number, lastChunkTime: number): Promise<void> {
    const now = Date.now();
    const elapsedMs = now - lastChunkTime;
    const expectedMs = (chunkSize / this.rateLimitBps) * 1000;
    const delayMs = Math.max(0, expectedMs - elapsedMs);

    if (delayMs > 0) {
      this.log('debug', `  Rate limiting: delaying ${delayMs.toFixed(0)}ms`);
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }

  /**
   * Clear the streaming queue (used when publisher reconnects)
   */
  clearQueue(): void {
    const queueLength = this.streamingQueue.length;
    if (queueLength > 0) {
      this.log('warn', `🗑️  Clearing ${queueLength} pending tasks from queue due to reconnection`);
      this.streamingQueue = [];
    }
    this.isProcessingQueue = false;
    this.log('info', '✅ FragmentChunker queue cleared and reset');
  }

  /**
   * Get streaming status
   */
  getStatus(): {
    isProcessing: boolean;
    queueLength: number;
    chunkSize: number;
    rateLimitBps: number;
  } {
    return {
      isProcessing: this.isProcessingQueue,
      queueLength: this.streamingQueue.length,
      chunkSize: this.chunkSize,
      rateLimitBps: this.rateLimitBps,
    };
  }

  // Typed event emitter methods
  on<K extends keyof FragmentChunkerEvents>(
    event: K,
    listener: FragmentChunkerEvents[K]
  ): this {
    return super.on(event, listener);
  }

  emit<K extends keyof FragmentChunkerEvents>(
    event: K,
    ...args: Parameters<FragmentChunkerEvents[K]>
  ): boolean {
    return super.emit(event, ...args);
  }
}

