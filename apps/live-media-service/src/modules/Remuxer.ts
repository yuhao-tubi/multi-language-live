/**
 * Remuxer Module
 * Combines video and processed audio into final output
 */
import { EventEmitter } from 'events';
import { spawn } from 'child_process';
import { ProcessedAudio, RemuxedOutput } from '../types/index.js';
import { StorageService } from '../services/storage.service.js';
import { getLogger } from '../utils/logger.js';

let logger: ReturnType<typeof getLogger> | null = null;

/**
 * Remuxer configuration
 */
export interface RemuxerConfig {
  /** Stream identifier */
  streamId: string;
  /** Storage service */
  storageService: StorageService;
  /** FFmpeg path */
  ffmpegPath?: string;
}

/**
 * Remuxer events
 */
export interface RemuxerEvents {
  'remux:complete': (output: RemuxedOutput) => void;
  'error': (error: Error) => void;
}

/**
 * Remuxer module
 * Remuxes video + processed audio into final output
 */
export class Remuxer extends EventEmitter {
  private config: RemuxerConfig;
  private storageService: StorageService;
  private ffmpegPath: string;

  constructor(config: RemuxerConfig) {
    super();
    this.config = config;
    this.storageService = config.storageService;
    this.ffmpegPath = config.ffmpegPath || 'ffmpeg';

    // Lazy initialize logger
    if (!logger) {
      try {
        logger = getLogger().child({ context: 'Remuxer' });
      } catch {
        logger = null;
      }
    }

    this.log('info', 'Remuxer initialized');
  }

  private log(level: 'debug' | 'info' | 'warn' | 'error', message: string, ...args: unknown[]): void {
    if (logger) {
      logger[level](message, ...args);
    }
  }

  /**
   * Process received processed audio
   */
  async onProcessedAudioReceived(processedAudio: ProcessedAudio): Promise<void> {
    try {
      const { batchNumber, audioPath } = processedAudio;

      this.log('info', `Remuxing batch ${batchNumber}`);

      // Get video path
      const videoPath = this.storageService.getVideoPath(this.config.streamId, batchNumber);

      // Check if video exists
      const videoExists = await this.storageService.fileExists(videoPath);
      if (!videoExists) {
        throw new Error(`Video file not found for batch ${batchNumber}: ${videoPath}`);
      }

      // Remux
      const output = await this.remux(batchNumber, videoPath, audioPath);

      this.log('info', `Remuxed batch ${batchNumber}: ${(output.size / 1024).toFixed(2)} KB`);

      this.emit('remux:complete', output);
    } catch (error) {
      this.log('error', `Failed to remux batch ${processedAudio.batchNumber}:`, error);
      this.emit('error', error as Error);
      throw error;
    }
  }

  /**
   * Remux video + audio into single file
   */
  private async remux(
    batchNumber: number,
    videoPath: string,
    audioPath: string
  ): Promise<RemuxedOutput> {
    this.log('debug', `Remuxing batch ${batchNumber}`);

    const outputPath = this.storageService.getOutputPath(this.config.streamId, batchNumber);
    await this.storageService.ensureDir(outputPath);

    // FFmpeg command to remux video + audio → output.mp4
    // Since both are demuxed from the same source, they should already be in sync
    const ffmpegArgs = [
      '-i', videoPath,
      '-i', audioPath,
      // Map both streams
      '-map', '0:v',
      '-map', '1:a',
      // Copy both streams without re-encoding
      '-c:v', 'copy',
      '-c:a', 'copy',
      // Use shortest stream as safeguard (in case of any drift)
      '-shortest',
      // Output format
      '-f', 'mp4',
      '-movflags', 'frag_keyframe+empty_moov',
      outputPath,
    ];

    await this.runFFmpeg(ffmpegArgs);

    // Get file size
    const size = await this.storageService.getFileSize(outputPath);

    const output: RemuxedOutput = {
      batchNumber,
      outputPath,
      size,
      timestamp: new Date(),
    };

    this.log('info', `Remuxed batch ${batchNumber}: ${(size / 1024).toFixed(2)} KB`);

    return output;
  }

  /**
   * Run FFmpeg command
   */
  private async runFFmpeg(args: string[]): Promise<void> {
    return new Promise((resolve, reject) => {
      this.log('debug', `Running FFmpeg: ${this.ffmpegPath} ${args.join(' ')}`);

      const ffmpeg = spawn(this.ffmpegPath, args);

      let stderr = '';

      ffmpeg.stderr.on('data', (data) => {
        stderr += data.toString();
      });

      ffmpeg.on('close', (code) => {
        if (code === 0) {
          resolve();
        } else {
          const error = new Error(`FFmpeg failed with code ${code}: ${stderr}`);
          this.log('error', 'FFmpeg error:', error);
          reject(error);
        }
      });

      ffmpeg.on('error', (error) => {
        this.log('error', 'FFmpeg spawn error:', error);
        reject(error);
      });
    });
  }

  // Typed event emitter methods
  on<K extends keyof RemuxerEvents>(
    event: K,
    listener: RemuxerEvents[K]
  ): this {
    return super.on(event, listener);
  }

  emit<K extends keyof RemuxerEvents>(
    event: K,
    ...args: Parameters<RemuxerEvents[K]>
  ): boolean {
    return super.emit(event, ...args);
  }
}

