/**
 * Stream Publisher Module
 * Publishes remuxed fragments to SRS via RTMP
 */
import { EventEmitter } from 'events';
import { spawn, ChildProcess } from 'child_process';
import fs from 'fs-extra';
import path from 'path';
import { RemuxedOutput } from '../types/index.js';
import { getLogger } from '../utils/logger.js';

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
}

/**
 * StreamPublisher events
 */
export interface StreamPublisherEvents {
  'fragment:published': (batchNumber: number) => void;
  'started': () => void;
  'stopped': () => void;
  'error': (error: Error) => void;
}

/**
 * StreamPublisher module
 * Publishes to SRS via RTMP
 */
export class StreamPublisher extends EventEmitter {
  private config: StreamPublisherConfig;
  private ffmpegPath: string;
  private ffmpegProcess: ChildProcess | null = null;
  private isPublishing: boolean = false;
  private concatListPath: string;
  private publishedCount: number = 0;

  constructor(config: StreamPublisherConfig) {
    super();
    this.config = config;
    this.ffmpegPath = config.ffmpegPath || 'ffmpeg';
    this.concatListPath = path.resolve('/tmp', `concat-${config.streamId}.txt`);

    // Lazy initialize logger
    if (!logger) {
      try {
        logger = getLogger().child({ context: 'StreamPublisher' });
      } catch {
        logger = null;
      }
    }

    this.log('info', 'StreamPublisher initialized');
  }

  private log(level: 'debug' | 'info' | 'warn' | 'error', message: string, ...args: unknown[]): void {
    if (logger) {
      logger[level](message, ...args);
    }
  }

  /**
   * Start publishing stream to SRS
   */
  async start(): Promise<void> {
    if (this.isPublishing) {
      this.log('warn', 'Already publishing');
      return;
    }

    this.log('info', `Starting RTMP publishing to: ${this.config.srsRtmpUrl}/${this.config.streamId}`);

    // Create empty concat list file
    await fs.writeFile(this.concatListPath, '');

    // Start FFmpeg process
    this.startFFmpegProcess();

    this.isPublishing = true;
    this.emit('started');
  }

  /**
   * Stop publishing
   */
  async stop(): Promise<void> {
    if (!this.isPublishing) {
      return;
    }

    this.log('info', 'Stopping RTMP publishing');

    if (this.ffmpegProcess) {
      this.ffmpegProcess.kill('SIGINT');
      this.ffmpegProcess = null;
    }

    // Clean up concat list file
    await fs.remove(this.concatListPath);

    this.isPublishing = false;
    this.emit('stopped');
  }

  /**
   * Publish a fragment
   */
  async publishFragment(output: RemuxedOutput): Promise<void> {
    if (!this.isPublishing) {
      throw new Error('Not currently publishing');
    }

    try {
      this.log('debug', `Publishing fragment ${output.batchNumber}`);

      // Append to concat list
      await fs.appendFile(
        this.concatListPath,
        `file '${output.outputPath}'\n`
      );

      // Send SIGHUP to FFmpeg to reload concat list
      if (this.ffmpegProcess && this.ffmpegProcess.pid) {
        process.kill(this.ffmpegProcess.pid, 'SIGHUP');
      }

      this.publishedCount++;
      this.log('info', `Published fragment ${output.batchNumber} (${this.publishedCount} total)`);

      this.emit('fragment:published', output.batchNumber);
    } catch (error) {
      this.log('error', `Failed to publish fragment ${output.batchNumber}:`, error);
      this.emit('error', error as Error);
      throw error;
    }
  }

  /**
   * Start FFmpeg process for continuous RTMP streaming
   */
  private startFFmpegProcess(): void {
    const rtmpUrl = `${this.config.srsRtmpUrl}/${this.config.streamId}`;

    const ffmpegArgs = [
      // Input from concat list (auto-reloading)
      '-re',
      '-f', 'concat',
      '-safe', '0',
      '-i', this.concatListPath,
      // Copy codecs (no re-encoding)
      '-c:v', 'copy',
      '-c:a', 'copy',
      // FLV output format for RTMP
      '-f', 'flv',
      rtmpUrl,
    ];

    this.log('debug', `Starting FFmpeg: ${this.ffmpegPath} ${ffmpegArgs.join(' ')}`);

    this.ffmpegProcess = spawn(this.ffmpegPath, ffmpegArgs);

    // Handle FFmpeg output
    this.ffmpegProcess.stdout?.on('data', (data) => {
      this.log('debug', `FFmpeg stdout: ${data}`);
    });

    this.ffmpegProcess.stderr?.on('data', (data) => {
      // FFmpeg writes logs to stderr
      const message = data.toString();
      // Only log errors, not normal progress messages
      if (message.includes('error') || message.includes('Error')) {
        this.log('error', `FFmpeg stderr: ${message}`);
      }
    });

    this.ffmpegProcess.on('close', (code) => {
      this.log('warn', `FFmpeg process exited with code ${code}`);
      this.isPublishing = false;
      
      if (code !== 0 && code !== null) {
        this.emit('error', new Error(`FFmpeg exited with code ${code}`));
      }
    });

    this.ffmpegProcess.on('error', (error) => {
      this.log('error', 'FFmpeg process error:', error);
      this.emit('error', error);
    });
  }

  /**
   * Get status
   */
  getStatus(): {
    isPublishing: boolean;
    publishedCount: number;
    rtmpUrl: string;
  } {
    return {
      isPublishing: this.isPublishing,
      publishedCount: this.publishedCount,
      rtmpUrl: `${this.config.srsRtmpUrl}/${this.config.streamId}`,
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

