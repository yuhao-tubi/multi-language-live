/**
 * Stream Fetcher Module
 * Fetches HLS stream segments and accumulates them into 30-second batches
 */
import { EventEmitter } from 'events';
import axios from 'axios';
import Parser from 'm3u8-parser';
import { SegmentMetadata, SegmentBatch } from '../types/index.js';
import { BufferManager } from '../services/buffer-manager.service.js';
import { StorageService } from '../services/storage.service.js';
import { getLogger } from '../utils/logger.js';

let logger: ReturnType<typeof getLogger> | null = null;

/**
 * StreamFetcher configuration
 */
export interface StreamFetcherConfig {
  /** HLS source URL */
  sourceUrl: string;
  /** Stream identifier */
  streamId: string;
  /** Buffer duration in seconds */
  bufferDurationSeconds: number;
  /** Storage service */
  storageService: StorageService;
  /** Poll interval in milliseconds */
  pollIntervalMs?: number;
}

/**
 * StreamFetcher events
 */
export interface StreamFetcherEvents {
  'batch:ready': (batch: SegmentBatch) => void;
  'segment:downloaded': (segment: SegmentMetadata) => void;
  'error': (error: Error) => void;
  'started': () => void;
  'stopped': () => void;
}

/**
 * StreamFetcher module
 * Fetches HLS segments and emits batches when buffer is full
 */
export class StreamFetcher extends EventEmitter {
  private config: StreamFetcherConfig;
  private bufferManager: BufferManager;
  private storageService: StorageService;
  private isRunning: boolean = false;
  private pollTimer: NodeJS.Timeout | null = null;
  private lastSequenceNumber: number = -1;
  private segmentCounter: number = 0;

  constructor(config: StreamFetcherConfig) {
    super();
    this.config = config;
    this.bufferManager = new BufferManager(config.bufferDurationSeconds);
    this.storageService = config.storageService;

    // Lazy initialize logger
    if (!logger) {
      try {
        logger = getLogger().child({ context: 'StreamFetcher' });
      } catch {
        logger = null;
      }
    }

    this.log('info', `StreamFetcher initialized for stream: ${config.streamId}`);
  }

  private log(level: 'debug' | 'info' | 'warn' | 'error', message: string, ...args: unknown[]): void {
    if (logger) {
      logger[level](message, ...args);
    }
  }

  /**
   * Start fetching stream
   */
  async start(): Promise<void> {
    if (this.isRunning) {
      this.log('warn', 'StreamFetcher already running');
      return;
    }

    this.isRunning = true;
    this.log('info', 'Starting stream fetching');
    
    this.emit('started');
    
    // Start polling
    await this.poll();
  }

  /**
   * Stop fetching stream
   */
  async stop(): Promise<void> {
    if (!this.isRunning) {
      return;
    }

    this.isRunning = false;
    
    if (this.pollTimer) {
      clearTimeout(this.pollTimer);
      this.pollTimer = null;
    }

    // Flush any remaining segments
    const batch = this.bufferManager.flush();
    if (batch) {
      this.emit('batch:ready', batch);
    }

    this.log('info', 'Stream fetching stopped');
    this.emit('stopped');
  }

  /**
   * Poll for new segments
   */
  private async poll(): Promise<void> {
    if (!this.isRunning) {
      return;
    }

    try {
      await this.fetchAndProcessManifest();
    } catch (error) {
      this.log('error', 'Error during poll:', error);
      this.emit('error', error as Error);
    }

    // Schedule next poll
    const pollInterval = this.config.pollIntervalMs || 2000; // 2 seconds default
    this.pollTimer = setTimeout(() => this.poll(), pollInterval);
  }

  /**
   * Fetch and process M3U8 manifest
   */
  private async fetchAndProcessManifest(): Promise<void> {
    this.log('debug', `Fetching manifest from: ${this.config.sourceUrl}`);

    // Fetch manifest
    const response = await axios.get(this.config.sourceUrl, {
      responseType: 'text',
      headers: {
        'User-Agent': 'live-media-service/1.0'
      }
    });

    // Parse manifest
    const parser = new Parser.Parser();
    parser.push(response.data);
    parser.end();

    const manifest = parser.manifest;

    // Check if this is a master playlist
    if (manifest.playlists && manifest.playlists.length > 0) {
      // This is a master playlist, we need to fetch the variant
      const variantUrl = this.resolveUrl(this.config.sourceUrl, manifest.playlists[0].uri);
      this.log('debug', `Master playlist detected, fetching variant: ${variantUrl}`);
      
      // Update source URL to variant and fetch again
      this.config.sourceUrl = variantUrl;
      return this.fetchAndProcessManifest();
    }

    // Process segments
    if (manifest.segments && manifest.segments.length > 0) {
      const baseMediaSequence = manifest.mediaSequence || 0;
      
      for (let i = 0; i < manifest.segments.length; i++) {
        const segment = manifest.segments[i];
        const segmentSequence = baseMediaSequence + i;
        
        // Skip if we've already processed this segment
        if (segmentSequence <= this.lastSequenceNumber) {
          continue;
        }

        // Download segment
        await this.downloadSegment(segment, segmentSequence);

        // Update last sequence number
        this.lastSequenceNumber = segmentSequence;
      }
    }
  }

  /**
   * Download a single segment
   */
  private async downloadSegment(segmentInfo: any, sequenceNumber: number): Promise<void> {
    try {
      // Resolve segment URL
      const segmentUrl = this.resolveUrl(this.config.sourceUrl, segmentInfo.uri);
      
      this.log('debug', `Downloading segment: ${segmentUrl}`);

      // Download segment data
      const response = await axios.get(segmentUrl, {
        responseType: 'arraybuffer',
        headers: {
          'User-Agent': 'live-media-service/1.0'
        }
      });

      const segmentData = Buffer.from(response.data);

      // Save segment to disk
      const segmentId = `seg-${this.segmentCounter++}`;
      const segmentPath = this.storageService.getSegmentPath(this.config.streamId, segmentId);
      await this.storageService.saveFile(segmentPath, segmentData);

      // Create segment metadata
      const segment: SegmentMetadata = {
        id: segmentId,
        path: segmentPath,
        size: segmentData.length,
        duration: segmentInfo.duration || 2, // Default to 2 seconds if not specified
        timestamp: new Date(),
        sequence: sequenceNumber,
      };

      this.log(
        'info',
        `Downloaded segment ${segment.id}: ${(segment.size / 1024).toFixed(2)} KB, ` +
        `${segment.duration.toFixed(2)}s`
      );

      this.emit('segment:downloaded', segment);

      // Add to buffer
      const batch = this.bufferManager.addSegment(segment);
      if (batch) {
        this.log('info', `Batch ready: ${batch.batchNumber} (${batch.totalDuration.toFixed(2)}s)`);
        this.emit('batch:ready', batch);
      }
    } catch (error) {
      this.log('error', `Failed to download segment: ${segmentInfo.uri}`, error);
      throw error;
    }
  }

  /**
   * Resolve relative URL against base URL
   */
  private resolveUrl(baseUrl: string, relativeUrl: string): string {
    if (relativeUrl.startsWith('http://') || relativeUrl.startsWith('https://')) {
      return relativeUrl;
    }

    try {
      const base = new URL(baseUrl);
      return new URL(relativeUrl, base).toString();
    } catch (error) {
      // Fallback: simple concatenation
      const basePath = baseUrl.substring(0, baseUrl.lastIndexOf('/') + 1);
      return basePath + relativeUrl;
    }
  }

  /**
   * Get buffer status
   */
  getStatus(): {
    isRunning: boolean;
    segmentCount: number;
    currentDuration: number;
    progress: number;
    nextBatchNumber: number;
    totalSegmentsDownloaded: number;
  } {
    const bufferStatus = this.bufferManager.getStatus();
    return {
      isRunning: this.isRunning,
      ...bufferStatus,
      totalSegmentsDownloaded: this.segmentCounter,
    };
  }

  /**
   * Force flush buffer
   */
  flush(): SegmentBatch | null {
    return this.bufferManager.flush();
  }

  // Typed event emitter methods
  on<K extends keyof StreamFetcherEvents>(
    event: K,
    listener: StreamFetcherEvents[K]
  ): this {
    return super.on(event, listener);
  }

  emit<K extends keyof StreamFetcherEvents>(
    event: K,
    ...args: Parameters<StreamFetcherEvents[K]>
  ): boolean {
    return super.emit(event, ...args);
  }
}

