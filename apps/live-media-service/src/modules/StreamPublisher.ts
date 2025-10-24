/**
 * Stream Publisher Module
 * Publishes remuxed fragments to SRS via RTMP using stdin piping
 */
import { EventEmitter } from 'events';
import { spawn, ChildProcess } from 'child_process';
import { once } from 'events';
import fs from 'fs-extra';
import path from 'path';
import { Writable } from 'stream';
import { RemuxedOutput } from '../types/index.js';
import { getLogger } from '../utils/logger.js';
import { FragmentChunker, FragmentChunkerConfig } from './FragmentChunker.js';

let logger: ReturnType<typeof getLogger> | null = null;

/**
 * StreamPublisher configuration
 */
export interface StreamPublisherConfig {
  /** Stream identifier */
  streamId: string;
  /** SRS RTMP URL (e.g., rtmp://localhost/live) */
  srsRtmpUrl: string;
  /** FFmpeg path */
  ffmpegPath?: string;
  /** Storage path for fragments */
  storagePath?: string;
  /** Output directory path (where batch files are stored) */
  outputDirectory?: string;
  /** Maximum reconnection attempts (default: 5) */
  maxReconnectAttempts?: number;
  /** Reconnection delay in ms (default: 2000) */
  reconnectDelayMs?: number;
  /** Maximum segments to keep in sliding window (0 = keep all, default: 20) */
  maxSegmentsToKeep?: number;
  /** Enable cleanup of old segments (default: true) */
  enableCleanup?: boolean;
  /** Safety buffer: extra segments to keep beyond maxSegmentsToKeep (default: 5) */
  cleanupSafetyBuffer?: number;
  /** Fragment chunker configuration for smooth stdin streaming */
  chunkerConfig?: FragmentChunkerConfig;
}

/**
 * StreamPublisher events
 */
export interface StreamPublisherEvents {
  'fragment:published': (batchNumber: number) => void;
  'started': () => void;
  'stopped': () => void;
  'reconnecting': (attempt: number) => void;
  'reconnected': () => void;
  'error': (error: Error) => void;
}

/**
 * StreamPublisher module
 * Publishes to SRS via RTMP using stdin piping
 */
export class StreamPublisher extends EventEmitter {
  private config: StreamPublisherConfig;
  private ffmpegPath: string;
  private ffmpegProcess: ChildProcess | null = null;
  private stdinStream: Writable | null = null;
  private isPublishing: boolean = false;
  private publishedCount: number = 0;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number;
  private reconnectDelayMs: number;
  private isReconnecting: boolean = false;
  private isStopping: boolean = false;
  private ffmpegStarted: boolean = false;
  
  // Storage for fragments
  private storagePath: string;
  private outputDirectory: string;
  
  // Sliding window cleanup
  private maxSegmentsToKeep: number;
  private enableCleanup: boolean;
  private cleanupSafetyBuffer: number;
  private publishedSegments: number[] = []; // Track published batch numbers
  
  // Fragment chunker for smooth streaming
  private fragmentChunker: FragmentChunker;

  constructor(config: StreamPublisherConfig) {
    super();
    this.config = config;
    this.ffmpegPath = config.ffmpegPath || 'ffmpeg';
    this.maxReconnectAttempts = config.maxReconnectAttempts ?? 5;
    this.reconnectDelayMs = config.reconnectDelayMs ?? 2000;
    this.storagePath = config.storagePath || './storage';
    
    // Sliding window cleanup configuration
    this.maxSegmentsToKeep = config.maxSegmentsToKeep ?? 3;
    this.enableCleanup = config.enableCleanup ?? true;
    this.cleanupSafetyBuffer = config.cleanupSafetyBuffer ?? 5;
    
    // Set output directory (where batch files are stored)
    this.outputDirectory = config.outputDirectory || this.storagePath;

    // Lazy initialize logger
    if (!logger) {
      try {
        logger = getLogger().child({ context: 'StreamPublisher' });
      } catch {
        logger = null;
      }
    }

    // Initialize fragment chunker for smooth streaming
    this.fragmentChunker = new FragmentChunker(config.chunkerConfig);

    this.log('info', 'StreamPublisher initialized (stdin piping mode with chunked streaming)');
    if (this.enableCleanup) {
      const totalKept = this.maxSegmentsToKeep + this.cleanupSafetyBuffer;
      this.log('info', `Sliding window cleanup enabled:`);
      this.log('info', `  - Target segments: ${this.maxSegmentsToKeep}`);
      this.log('info', `  - Safety buffer: ${this.cleanupSafetyBuffer}`);
      this.log('info', `  - Total kept: ${totalKept}`);
    } else {
      this.log('info', 'Cleanup disabled: all segments will be retained');
    }
  }

  private log(level: 'debug' | 'info' | 'warn' | 'error', message: string, ...args: unknown[]): void {
    if (logger) {
      logger[level](message, ...args);
    }
  }

  /**
   * Start publishing - starts FFmpeg with stdin ready
   */
  async start(): Promise<void> {
    if (this.isPublishing) {
      this.log('warn', 'Already publishing');
      return;
    }

    this.log('info', `Initializing RTMP publishing to: ${this.config.srsRtmpUrl}/${this.config.streamId}`);
    this.log('info', 'Using stdin piping for fragments');

    try {
      // Ensure storage directory exists
      await fs.ensureDir(this.storagePath);
      
      // Start FFmpeg process with stdin ready
      await this.startFFmpegProcess();
      
      this.isPublishing = true;
      this.ffmpegStarted = true;
      this.reconnectAttempts = 0;
      
      this.emit('started');
      this.log('info', '✅ Publisher started, FFmpeg ready to receive fragments via stdin');
    } catch (error) {
      this.log('error', 'Failed to start publisher:', error);
      throw error;
    }
  }

  /**
   * Stop publishing gracefully
   */
  async stop(): Promise<void> {
    if (!this.isPublishing) {
      this.log('debug', 'Stop called but not currently publishing');
      return;
    }

    this.isStopping = true;
    this.log('info', '🛑 Stopping RTMP publishing...');
    this.log('info', `Stop state: publishedCount=${this.publishedCount}, ffmpegStarted=${this.ffmpegStarted}`);

    try {
      // Close stdin gracefully
      if (this.stdinStream) {
        this.log('debug', 'Closing stdin stream...');
        this.stdinStream.end();
        this.stdinStream = null;
      }

      // Stop FFmpeg process
      if (this.ffmpegProcess) {
        const pid = this.ffmpegProcess.pid;
        this.log('info', `Terminating FFmpeg process (PID: ${pid}) with SIGTERM`);
        this.ffmpegProcess.kill('SIGTERM');

        // Wait for FFmpeg to finish processing (with timeout)
        this.log('debug', 'Waiting for FFmpeg to close (5s timeout)...');
        await Promise.race([
          once(this.ffmpegProcess, 'close'),
          new Promise((resolve) => setTimeout(resolve, 5000))
        ]);

        // Force kill if still running
        if (this.ffmpegProcess && !this.ffmpegProcess.killed) {
          this.log('warn', `Force killing FFmpeg process (PID: ${pid}) with SIGKILL`);
          this.ffmpegProcess.kill('SIGKILL');
        } else {
          this.log('debug', 'FFmpeg process terminated gracefully');
        }

        this.ffmpegProcess = null;
      } else {
        this.log('debug', 'No FFmpeg process to stop');
      }

      this.isPublishing = false;
      this.isStopping = false;
      this.ffmpegStarted = false;

      this.log('info', '✅ Publisher stopped successfully');
      this.emit('stopped');
    } catch (error) {
      this.log('error', 'Error during publisher stop:', error);
      this.isStopping = false; // Reset flag on error
      throw error;
    }
  }

  /**
   * Publish a fragment by streaming it to FFmpeg stdin in chunks
   */
  async publishFragment(output: RemuxedOutput): Promise<void> {
    if (this.isReconnecting) {
      this.log('warn', `Publisher is reconnecting, skipping fragment ${output.batchNumber}`);
      return;
    }

    if (!this.isPublishing || !this.stdinStream) {
      this.log('warn', `Not publishing or stdin not ready, skipping fragment ${output.batchNumber}`);
      return;
    }

    try {
      this.log('debug', `Publishing fragment ${output.batchNumber} via stdin (chunked)`);

      // Verify fragment file exists
      if (!(await fs.pathExists(output.outputPath))) {
        throw new Error(`Fragment file does not exist: ${output.outputPath}`);
      }

      const fragmentStats = await fs.stat(output.outputPath);
      
      this.log('debug', `Fragment ${output.batchNumber} details:`, {
        path: output.outputPath,
        size: fragmentStats.size,
        exists: true
      });

      // Stream fragment in chunks using FragmentChunker
      await this.fragmentChunker.streamFragment(
        output.outputPath,
        this.stdinStream,
        output.batchNumber
      );

      this.publishedCount++;
      
      this.log('info', `📡 Published fragment ${output.batchNumber} (${(fragmentStats.size / 1024).toFixed(2)} KB, ${this.publishedCount} total)`);

      // Track published segment
      this.publishedSegments.push(output.batchNumber);
      
      // Perform sliding window cleanup if enabled
      if (this.enableCleanup && this.maxSegmentsToKeep > 0) {
        await this.performCleanup();
      }

      this.emit('fragment:published', output.batchNumber);
    } catch (error) {
      this.log('error', `Failed to publish fragment ${output.batchNumber}:`, error);
      
      // Attempt reconnection if FFmpeg died
      if (this.isPublishing && this.shouldReconnect(error as Error)) {
        this.log('warn', 'FFmpeg failure detected, attempting reconnection');
        await this.reconnect();
      } else {
        this.emit('error', error as Error);
        throw error;
      }
    }
  }

  /**
   * Start FFmpeg process with stdin input
   */
  private async startFFmpegProcess(): Promise<void> {
    const rtmpUrl = `${this.config.srsRtmpUrl}/${this.config.streamId}`;

    const ffmpegArgs = [
      '-hide_banner',
      '-loglevel', 'info',
      // Input from stdin
      '-re',                              // Read input at native frame rate
      '-f', 'mp4',                        // Input format is MP4 (fragmented)
      '-fflags', '+genpts', 
      '-copyts',
      '-start_at_zero',
      '-i', 'pipe:0',                     // Read from stdin
      // Copy codecs (fragments are already encoded properly)
      '-c:v', 'copy',                     // Copy video codec
      '-c:a', 'copy',                     // Copy audio codec
      // Timestamp and sync flags for continuity
      '-fflags', '+genpts',               // Generate presentation timestamps
      '-avoid_negative_ts', 'make_zero',  // Ensure positive timestamps
      // FLV output format for RTMP
      '-f', 'flv',
      '-flvflags', 'no_duration_filesize',  // Don't require total duration
      rtmpUrl,
    ];

    // Log full command for troubleshooting
    const fullCommand = `${this.ffmpegPath} ${ffmpegArgs.join(' ')}`;
    this.log('info', '🎬 Full FFmpeg command:');
    this.log('info', fullCommand);
    this.log('info', `RTMP target: ${rtmpUrl}`);

    this.ffmpegProcess = spawn(this.ffmpegPath, ffmpegArgs);
    
    if (!this.ffmpegProcess.stdin) {
      throw new Error('Failed to open stdin stream for FFmpeg');
    }

    // Store stdin stream reference
    this.stdinStream = this.ffmpegProcess.stdin;
    
    this.log('info', `FFmpeg process spawned with PID: ${this.ffmpegProcess.pid}`);

    // Handle stdin errors
    this.stdinStream.on('error', (error) => {
      this.log('error', 'stdin stream error:', error);
      this.handleFFmpegFailure(error);
    });

    // Accumulate stderr for error detection
    let stderrBuffer = '';
    let stdoutBuffer = '';

    // Handle FFmpeg stdout
    this.ffmpegProcess.stdout?.on('data', (data) => {
      const message = data.toString();
      stdoutBuffer += message;
      this.log('debug', `FFmpeg stdout: ${message.trim()}`);
    });

    // Handle FFmpeg stderr (errors and warnings)
    this.ffmpegProcess.stderr?.on('data', (data) => {
      const message = data.toString();
      stderrBuffer += message;

      // Log all FFmpeg output for debugging
      this.log('debug', `FFmpeg stderr: ${message.trim()}`);

      // Check for critical errors
      if (message.toLowerCase().includes('invalid data found') ||
          message.toLowerCase().includes('no such file') ||
          message.toLowerCase().includes('cannot read')) {
        this.log('error', `FFmpeg ERROR: ${message.trim()}`);
      } else if (message.toLowerCase().includes('error') && !message.toLowerCase().includes('last message repeated')) {
        this.log('error', `FFmpeg ERROR: ${message.trim()}`);
      } else if (message.toLowerCase().includes('warning')) {
        this.log('warn', `FFmpeg WARNING: ${message.trim()}`);
      }
    });

    // Handle FFmpeg process exit
    this.ffmpegProcess.on('close', (code, signal) => {
      this.log('warn', `FFmpeg process exited - code: ${code}, signal: ${signal}`);
      this.log('warn', `Exit context: isStopping=${this.isStopping}, isReconnecting=${this.isReconnecting}, publishedCount=${this.publishedCount}`);
      
      // Log buffer contents for debugging
      if (stderrBuffer.trim()) {
        this.log('debug', `FFmpeg stderr buffer (last 500 chars): ${stderrBuffer.substring(Math.max(0, stderrBuffer.length - 500))}`);
      }
      if (stdoutBuffer.trim()) {
        this.log('debug', `FFmpeg stdout buffer (last 500 chars): ${stdoutBuffer.substring(Math.max(0, stdoutBuffer.length - 500))}`);
      }
      
      if (!this.isStopping && !this.isReconnecting) {
        this.log('error', `FFmpeg exited unexpectedly while publishing`);
        const error = new Error(`FFmpeg exited unexpectedly (code: ${code}, signal: ${signal})`);
        this.handleFFmpegFailure(error);
      } else {
        this.log('info', 'FFmpeg exited during shutdown/reconnect - expected behavior');
      }
    });

    this.ffmpegProcess.on('error', (error) => {
      this.log('error', 'FFmpeg process error:', error);
      this.handleFFmpegFailure(error);
    });

    // Give FFmpeg a moment to start
    await new Promise((resolve) => setTimeout(resolve, 100));

    this.log('info', '✅ FFmpeg process started with stdin piping');
  }

  /**
   * Perform sliding window cleanup of old segments
   * Keeps only the latest N segments on disk
   */
  private async performCleanup(): Promise<void> {
    try {
      const totalSegmentsToKeep = this.maxSegmentsToKeep + this.cleanupSafetyBuffer;
      
      // Only cleanup if we exceed the threshold
      if (this.publishedSegments.length <= totalSegmentsToKeep) {
        return;
      }

      // Determine which segments to remove (oldest ones)
      const segmentsToRemove = this.publishedSegments.slice(0, this.publishedSegments.length - totalSegmentsToKeep);
      
      if (segmentsToRemove.length === 0) {
        return;
      }

      this.log('info', `🧹 Cleaning up ${segmentsToRemove.length} old segments (keeping last ${totalSegmentsToKeep})`);

      // Remove old batch files from disk
      let deletedCount = 0;
      for (const batchNumber of segmentsToRemove) {
        const batchPath = path.join(this.outputDirectory, `batch-${batchNumber}.mp4`);
        
        try {
          if (await fs.pathExists(batchPath)) {
            await fs.remove(batchPath);
            deletedCount++;
            this.log('debug', `  Deleted: batch-${batchNumber}.mp4`);
          }
        } catch (error) {
          this.log('warn', `  Failed to delete batch-${batchNumber}.mp4:`, error);
        }
      }

      // Update published segments array to only keep recent ones
      this.publishedSegments = this.publishedSegments.slice(-totalSegmentsToKeep);

      this.log('info', `✅ Cleanup complete: deleted ${deletedCount} old segments, ${this.publishedSegments.length} segments retained`);
    } catch (error) {
      this.log('error', 'Error during cleanup:', error);
      // Don't throw - cleanup failures shouldn't stop the pipeline
    }
  }

  /**
   * Check if error warrants reconnection attempt
   */
  private shouldReconnect(error: Error): boolean {
    const errorMessage = error.message.toLowerCase();
    
    // Common errors that should trigger reconnection
    const reconnectableErrors = [
      'ffmpeg exited',
      'process error',
      'connection reset',
      'stdin',
      'pipe',
      'enoent',
    ];

    return reconnectableErrors.some((msg) => errorMessage.includes(msg));
  }

  /**
   * Handle FFmpeg failure with reconnection logic
   */
  private async handleFFmpegFailure(error: Error): Promise<void> {
    this.log('error', '🔴 handleFFmpegFailure called', {
      error: error.message,
      isStopping: this.isStopping,
      isReconnecting: this.isReconnecting,
      isPublishing: this.isPublishing,
      reconnectAttempts: this.reconnectAttempts
    });
    
    if (this.isStopping || this.isReconnecting) {
      this.log('info', 'Skipping failure handling - already stopping or reconnecting');
      return;
    }

    this.log('error', 'FFmpeg failure detected:', error);
    this.emit('error', error);

    // Attempt reconnection if we haven't exceeded max attempts
    if (this.isPublishing && this.reconnectAttempts < this.maxReconnectAttempts) {
      this.log('warn', `Will attempt reconnection (${this.reconnectAttempts + 1}/${this.maxReconnectAttempts})`);
      await this.reconnect();
    } else if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.log('error', `❌ Max reconnection attempts (${this.maxReconnectAttempts}) reached, giving up`);
      this.isPublishing = false;
      this.emit('error', new Error('Max reconnection attempts reached'));
    } else {
      this.log('warn', `Not reconnecting: isPublishing=${this.isPublishing}, reconnectAttempts=${this.reconnectAttempts}`);
    }
  }

  /**
   * Reconnect FFmpeg process
   */
  private async reconnect(): Promise<void> {
    if (this.isReconnecting) {
      this.log('warn', 'Reconnection already in progress, skipping duplicate attempt');
      return;
    }

    this.isReconnecting = true;
    this.reconnectAttempts++;

    this.log('warn', `🔄 Starting reconnection attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);
    this.log('info', `Reconnection state: ffmpegStarted=${this.ffmpegStarted}, publishedCount=${this.publishedCount}, isPublishing=${this.isPublishing}`);
    this.emit('reconnecting', this.reconnectAttempts);

    try {
      // Clean up old process and stdin stream
      if (this.stdinStream) {
        this.log('debug', 'Cleaning up old stdin stream');
        this.stdinStream.removeAllListeners();
        this.stdinStream = null;
      }

      if (this.ffmpegProcess) {
        const oldPid = this.ffmpegProcess.pid;
        this.log('debug', `Cleaning up old FFmpeg process (PID: ${oldPid})`);
        this.ffmpegProcess.removeAllListeners();
        this.ffmpegProcess.kill('SIGKILL');
        this.ffmpegProcess = null;
        this.log('debug', `Old FFmpeg process killed`);
      }

      // Clear FragmentChunker queue to remove any pending tasks with old stdin stream
      this.log('info', '🔄 Clearing FragmentChunker queue before reconnection...');
      this.fragmentChunker.clearQueue();

      // Wait before reconnecting
      this.log('debug', `Waiting ${this.reconnectDelayMs}ms before reconnecting...`);
      await new Promise((resolve) => setTimeout(resolve, this.reconnectDelayMs));

      // Start new FFmpeg process with stdin ready
      this.log('info', 'Starting new FFmpeg process with stdin...');
      await this.startFFmpegProcess();

      this.log('info', '✅ Reconnected successfully, stdin ready for fragments');
      this.emit('reconnected');
      this.reconnectAttempts = 0; // Reset counter on success
    } catch (error) {
      this.log('error', `Reconnection attempt ${this.reconnectAttempts} failed:`, error);
      
      // Try again if we haven't hit the limit
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.log('warn', `Will retry reconnection (${this.reconnectAttempts}/${this.maxReconnectAttempts} attempts used)`);
        this.isReconnecting = false; // Reset flag to allow retry
        await this.reconnect();
      } else {
        this.log('error', 'Max reconnection attempts reached, not retrying');
      }
    } finally {
      this.isReconnecting = false;
    }
  }

  /**
   * Get status
   */
  getStatus(): {
    isPublishing: boolean;
    publishedCount: number;
    rtmpUrl: string;
    reconnectAttempts: number;
    isReconnecting: boolean;
    ffmpegStarted: boolean;
    stdinReady: boolean;
  } {
    return {
      isPublishing: this.isPublishing,
      publishedCount: this.publishedCount,
      rtmpUrl: `${this.config.srsRtmpUrl}/${this.config.streamId}`,
      reconnectAttempts: this.reconnectAttempts,
      isReconnecting: this.isReconnecting,
      ffmpegStarted: this.ffmpegStarted,
      stdinReady: this.stdinStream !== null,
    };
  }

  // Typed event emitter methods
  on<K extends keyof StreamPublisherEvents>(
    event: K,
    listener: StreamPublisherEvents[K]
  ): this {
    return super.on(event, listener);
  }

  emit<K extends keyof StreamPublisherEvents>(
    event: K,
    ...args: Parameters<StreamPublisherEvents[K]>
  ): boolean {
    return super.emit(event, ...args);
  }
}

