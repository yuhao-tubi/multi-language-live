/**
 * Audio Processor Module
 * Demuxes TS batches into video + audio FMP4 and sends audio for processing
 */
import { EventEmitter } from 'events';
import { spawn } from 'child_process';
import { SegmentBatch, DemuxedOutput, ProcessedAudio } from '../types/index.js';
import { FragmentMetadata } from '../types/protocol.js';
import { StorageService } from '../services/storage.service.js';
import { SocketClientService } from '../services/socket-client.service.js';
import { getLogger } from '../utils/logger.js';

let logger: ReturnType<typeof getLogger> | null = null;

/**
 * AudioProcessor configuration
 */
export interface AudioProcessorConfig {
  /** Stream identifier */
  streamId: string;
  /** Storage service */
  storageService: StorageService;
  /** Socket client service */
  socketClient: SocketClientService;
  /** FFmpeg path */
  ffmpegPath?: string;
}

/**
 * AudioProcessor events
 */
export interface AudioProcessorEvents {
  'demux:complete': (output: DemuxedOutput) => void;
  'audio:sent': (batchNumber: number) => void;
  'audio:processed': (processed: ProcessedAudio) => void;
  'error': (error: Error) => void;
}

/**
 * AudioProcessor module
 * Demuxes batches and sends audio for processing
 */
export class AudioProcessor extends EventEmitter {
  private config: AudioProcessorConfig;
  private storageService: StorageService;
  private socketClient: SocketClientService;
  private ffmpegPath: string;

  constructor(config: AudioProcessorConfig) {
    super();
    this.config = config;
    this.storageService = config.storageService;
    this.socketClient = config.socketClient;
    this.ffmpegPath = config.ffmpegPath || 'ffmpeg';

    // Lazy initialize logger
    if (!logger) {
      try {
        logger = getLogger().child({ context: 'AudioProcessor' });
      } catch {
        logger = null;
      }
    }

    // Set up socket client event handlers
    this.setupSocketHandlers();

    this.log('info', 'AudioProcessor initialized');
  }

  private log(level: 'debug' | 'info' | 'warn' | 'error', message: string, ...args: unknown[]): void {
    if (logger) {
      logger[level](message, ...args);
    }
  }

  /**
   * Process a batch: concatenate segments, demux, and send audio
   */
  async processBatch(batch: SegmentBatch): Promise<void> {
    try {
      this.log('info', `Processing batch ${batch.batchNumber} (${batch.segments.length} segments)`);

      // 1. Concatenate segments
      const concatenatedPath = await this.concatenateSegments(batch);

      // 2. Demux into video + audio
      const demuxed = await this.demux(batch.batchNumber, concatenatedPath);

      this.emit('demux:complete', demuxed);

      // 3. Send audio for processing
      await this.sendAudioForProcessing(batch.batchNumber, demuxed.audioPath);

      this.emit('audio:sent', batch.batchNumber);

      this.log('info', `Batch ${batch.batchNumber} processing initiated`);
    } catch (error) {
      this.log('error', `Failed to process batch ${batch.batchNumber}:`, error);
      this.emit('error', error as Error);
      throw error;
    }
  }

  /**
   * Concatenate segment files into single TS file
   */
  private async concatenateSegments(batch: SegmentBatch): Promise<string> {
    this.log('debug', `Concatenating ${batch.segments.length} segments`);

    const batchPath = this.storageService.getBatchPath(this.config.streamId, batch.batchNumber);
    await this.storageService.ensureDir(batchPath);

    // Read and concatenate all segments
    const buffers: Buffer[] = [];
    for (const segment of batch.segments) {
      const data = await this.storageService.readFile(segment.path);
      buffers.push(data);
    }

    const concatenated = Buffer.concat(buffers);
    await this.storageService.saveFile(batchPath, concatenated);

    this.log('info', `Concatenated batch ${batch.batchNumber}: ${(concatenated.length / 1024 / 1024).toFixed(2)} MB`);

    return batchPath;
  }

  /**
   * Demux TS file into separate video and audio FMP4 files
   */
  private async demux(batchNumber: number, inputPath: string): Promise<DemuxedOutput> {
    this.log('debug', `Demuxing batch ${batchNumber}`);

    const videoPath = this.storageService.getVideoPath(this.config.streamId, batchNumber);
    const audioPath = this.storageService.getAudioPath(this.config.streamId, batchNumber);

    await this.storageService.ensureDir(videoPath);
    await this.storageService.ensureDir(audioPath);

    // FFmpeg command to demux TS → video.fmp4 + audio.fmp4
    const ffmpegArgs = [
      '-i', inputPath,
      // Video output
      '-map', '0:v',
      '-c:v', 'copy',
      '-f', 'mp4',
      '-movflags', 'frag_keyframe+empty_moov',
      videoPath,
      // Audio output
      '-map', '0:a',
      '-c:a', 'copy',
      '-f', 'mp4',
      '-movflags', 'frag_keyframe+empty_moov',
      audioPath,
    ];

    await this.runFFmpeg(ffmpegArgs);

    // Get file sizes
    const videoSize = await this.storageService.getFileSize(videoPath);
    const audioSize = await this.storageService.getFileSize(audioPath);

    const output: DemuxedOutput = {
      batchNumber,
      videoPath,
      audioPath,
      videoSize,
      audioSize,
      timestamp: new Date(),
    };

    this.log('info', 
      `Demuxed batch ${batchNumber}: ` +
      `video=${(videoSize / 1024).toFixed(2)} KB, ` +
      `audio=${(audioSize / 1024).toFixed(2)} KB`
    );

    return output;
  }

  /**
   * Send audio file for processing via WebSocket
   */
  private async sendAudioForProcessing(batchNumber: number, audioPath: string): Promise<void> {
    this.log('debug', `Sending audio for batch ${batchNumber}`);

    // Read audio data
    const audioData = await this.storageService.readFile(audioPath);

    // Create fragment metadata
    const fragment: FragmentMetadata = {
      id: `${this.config.streamId}_batch-${batchNumber}`,
      streamId: this.config.streamId,
      batchNumber,
      contentType: 'audio/mp4',
      size: audioData.length,
      duration: 30, // Approximate - we could parse this from the file if needed
      timestamp: new Date().toISOString(),
    };

    // Send via WebSocket
    await this.socketClient.sendFragment(fragment, audioData);

    this.log('info', `Sent audio for batch ${batchNumber} (${(audioData.length / 1024).toFixed(2)} KB)`);
  }

  /**
   * Set up socket client event handlers
   */
  private setupSocketHandlers(): void {
    this.socketClient.on('fragment:processed', (event) => {
      this.handleProcessedAudio(event);
    });

    this.socketClient.on('fragment:error', (event) => {
      this.log('error', `Audio processing error for ${event.fragment.id}: ${event.error}`);
      this.emit('error', new Error(`Audio processing failed: ${event.error}`));
    });
  }

  /**
   * Handle received processed audio
   */
  private async handleProcessedAudio(event: any): Promise<void> {
    try {
      const { fragment, data } = event;
      const batchNumber = fragment.batchNumber;

      this.log('info', `Received processed audio for batch ${batchNumber}`);

      // Save processed audio
      const processedAudioPath = this.storageService.getProcessedAudioPath(
        this.config.streamId,
        batchNumber
      );
      await this.storageService.saveFile(processedAudioPath, data);

      const processed: ProcessedAudio = {
        batchNumber,
        audioPath: processedAudioPath,
        size: data.length,
        timestamp: new Date(),
        metadata: event.metadata,
      };

      this.log('info', 
        `Saved processed audio for batch ${batchNumber}: ${(data.length / 1024).toFixed(2)} KB`
      );

      this.emit('audio:processed', processed);
    } catch (error) {
      this.log('error', 'Failed to handle processed audio:', error);
      this.emit('error', error as Error);
    }
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
  on<K extends keyof AudioProcessorEvents>(
    event: K,
    listener: AudioProcessorEvents[K]
  ): this {
    return super.on(event, listener);
  }

  emit<K extends keyof AudioProcessorEvents>(
    event: K,
    ...args: Parameters<AudioProcessorEvents[K]>
  ): boolean {
    return super.emit(event, ...args);
  }
}

