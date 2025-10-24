/**
 * Pipeline Orchestrator
 * Coordinates all processing modules for end-to-end live stream processing
 */
import { EventEmitter } from 'events';
import { PipelineConfig, PipelineStatus, PipelineStats } from '../types/index.js';
import { StorageService } from '../services/storage.service.js';
import { SocketClientService } from '../services/socket-client.service.js';
import { StreamFetcher } from './StreamFetcher.js';
import { AudioProcessor } from './AudioProcessor.js';
import { Remuxer } from './Remuxer.js';
import { StreamPublisher } from './StreamPublisher.js';
import { getLogger } from '../utils/logger.js';

let logger: ReturnType<typeof getLogger> | null = null;

/**
 * Pipeline Orchestrator events
 */
export interface PipelineOrchestratorEvents {
  'started': () => void;
  'stopped': () => void;
  'error': (error: Error) => void;
  'status:update': (status: PipelineStatus) => void;
}

/**
 * Pipeline Orchestrator
 * Manages the complete processing pipeline
 */
export class PipelineOrchestrator extends EventEmitter {
  private config: PipelineConfig;
  
  // Services
  private storageService: StorageService;
  private socketClient: SocketClientService;
  
  // Modules
  private streamFetcher: StreamFetcher;
  private audioProcessor: AudioProcessor;
  private remuxer: Remuxer;
  private streamPublisher: StreamPublisher;
  
  // State
  private isRunning: boolean = false;
  private startTime: Date | null = null;
  private stats: PipelineStats;
  private lastError: string | null = null;
  private currentPhase: PipelineStatus['phase'] = 'idle';

  constructor(config: PipelineConfig) {
    super();
    this.config = config;

    // Lazy initialize logger
    if (!logger) {
      try {
        logger = getLogger().child({ context: 'PipelineOrchestrator' });
      } catch {
        logger = null;
      }
    }

    // Initialize stats
    this.stats = {
      segmentsFetched: 0,
      batchesProcessed: 0,
      fragmentsPublished: 0,
      bytesProcessed: 0,
      avgProcessingTime: 0,
      currentBufferSize: 0,
    };

    // Initialize services
    this.storageService = new StorageService({
      basePath: config.storagePath,
      originalStreamPath: `${config.storagePath}/original_stream`,
      processedFragmentsPath: `${config.storagePath}/processed_fragments`,
      logsPath: `${config.storagePath}/logs`,
    });

    this.socketClient = new SocketClientService({
      serverUrl: config.audioProcessorUrl,
      reconnectAttempts: 5,
      reconnectDelayMs: 2000,
    });

    // Initialize modules
    this.streamFetcher = new StreamFetcher({
      sourceUrl: config.sourceUrl,
      streamId: config.streamId,
      bufferDurationSeconds: config.bufferDuration,
      storageService: this.storageService,
    });

    this.audioProcessor = new AudioProcessor({
      streamId: config.streamId,
      storageService: this.storageService,
      socketClient: this.socketClient,
      bufferDurationSeconds: config.bufferDuration,
    });

    this.remuxer = new Remuxer({
      streamId: config.streamId,
      storageService: this.storageService,
    });

    this.streamPublisher = new StreamPublisher({
      streamId: config.streamId,
      srsRtmpUrl: config.srsRtmpUrl,
      storagePath: config.storagePath,
      outputDirectory: this.storageService.getOutputDirectory(config.streamId),
    });

    // Set up event handlers
    this.setupEventHandlers();

    this.log('info', 'Pipeline Orchestrator initialized');
  }

  private log(level: 'debug' | 'info' | 'warn' | 'error', message: string, ...args: unknown[]): void {
    if (logger) {
      logger[level](message, ...args);
    }
  }

  /**
   * Start the pipeline
   */
  async start(): Promise<void> {
    if (this.isRunning) {
      this.log('warn', 'Pipeline already running');
      return;
    }

    try {
      this.log('info', '🚀 Starting pipeline...');
      this.log('info', `   Source: ${this.config.sourceUrl}`);
      this.log('info', `   Stream ID: ${this.config.streamId}`);
      this.log('info', `   Buffer: ${this.config.bufferDuration}s`);
      this.log('info', `   Audio Processor: ${this.config.audioProcessorUrl}`);
      this.log('info', `   SRS: ${this.config.srsRtmpUrl}/${this.config.streamId}`);

      // Initialize storage
      await this.storageService.initialize();
      this.log('info', '✓ Storage initialized');

      // Connect to audio processor
      await this.socketClient.connect();
      this.log('info', '✓ Connected to audio processor');

      // Start stream publisher
      await this.streamPublisher.start();
      this.log('info', '✓ Stream publisher started');

      // Start stream fetcher (this triggers the whole pipeline)
      await this.streamFetcher.start();
      this.log('info', '✓ Stream fetcher started');

      this.isRunning = true;
      this.startTime = new Date();
      this.currentPhase = 'fetching';
      this.lastError = null;

      this.log('info', '✅ Pipeline started successfully');
      this.emit('started');

      // Emit initial status
      this.emitStatusUpdate();
    } catch (error) {
      this.log('error', 'Failed to start pipeline:', error);
      this.lastError = (error as Error).message;
      this.currentPhase = 'error';
      this.emit('error', error as Error);
      throw error;
    }
  }

  /**
   * Stop the pipeline
   */
  async stop(): Promise<void> {
    if (!this.isRunning) {
      return;
    }

    this.log('info', '🛑 Stopping pipeline...');

    try {
      // Stop in reverse order
      await this.streamFetcher.stop();
      this.log('info', '✓ Stream fetcher stopped');

      await this.streamPublisher.stop();
      this.log('info', '✓ Stream publisher stopped');

      this.socketClient.disconnect();
      this.log('info', '✓ Disconnected from audio processor');

      this.isRunning = false;
      this.currentPhase = 'idle';

      this.log('info', '✅ Pipeline stopped');
      this.emit('stopped');

      // Emit final status
      this.emitStatusUpdate();
    } catch (error) {
      this.log('error', 'Error stopping pipeline:', error);
      this.emit('error', error as Error);
    }
  }

  /**
   * Set up event handlers to connect modules
   */
  private setupEventHandlers(): void {
    // StreamFetcher → AudioProcessor
    this.streamFetcher.on('batch:ready', async (batch) => {
      this.log('info', `📦 Batch ready: ${batch.batchNumber}`);
      this.currentPhase = 'processing';
      this.stats.batchesProcessed++;
      
      try {
        await this.audioProcessor.processBatch(batch);
      } catch (error) {
        this.log('error', 'Error processing batch:', error);
        this.handleError(error as Error);
      }
      
      this.emitStatusUpdate();
    });

    this.streamFetcher.on('segment:downloaded', (segment) => {
      this.stats.segmentsFetched++;
      this.stats.bytesProcessed += segment.size;
      this.stats.currentBufferSize = this.streamFetcher.getStatus().currentDuration;
    });

    // AudioProcessor → Remuxer
    this.audioProcessor.on('audio:processed', async (processed) => {
      this.log('info', `🎵 Audio processed: batch ${processed.batchNumber}`);
      
      try {
        await this.remuxer.onProcessedAudioReceived(processed);
      } catch (error) {
        this.log('error', 'Error remuxing:', error);
        this.handleError(error as Error);
      }
    });

    // Remuxer → StreamPublisher
    this.remuxer.on('remux:complete', async (output) => {
      this.log('info', `🎬 Remux complete: batch ${output.batchNumber}`);
      this.currentPhase = 'publishing';
      
      try {
        await this.streamPublisher.publishFragment(output);
      } catch (error) {
        this.log('error', 'Error publishing:', error);
        this.handleError(error as Error);
      }
      
      this.emitStatusUpdate();
    });

    // StreamPublisher events
    this.streamPublisher.on('fragment:published', (batchNumber) => {
      this.log('info', `📡 Published: batch ${batchNumber}`);
      this.stats.fragmentsPublished++;
      this.currentPhase = 'fetching'; // Back to waiting for next batch
      this.emitStatusUpdate();
    });

    this.streamPublisher.on('reconnecting', (attempt) => {
      this.log('warn', `🔄 Publisher reconnecting (attempt ${attempt})`);
      this.currentPhase = 'error';
      this.lastError = `Publisher reconnecting (attempt ${attempt})`;
      this.emitStatusUpdate();
    });

    this.streamPublisher.on('reconnected', () => {
      this.log('info', '✅ Publisher reconnected successfully');
      this.currentPhase = 'publishing';
      this.lastError = null;
      this.emitStatusUpdate();
    });

    // Error handlers
    this.streamFetcher.on('error', (error) => this.handleError(error));
    this.audioProcessor.on('error', (error) => this.handleError(error));
    this.remuxer.on('error', (error) => this.handleError(error));
    this.streamPublisher.on('error', (error) => this.handleError(error));
    this.socketClient.on('error', (error) => this.handleError(error));
  }

  /**
   * Handle errors from any module
   */
  private handleError(error: Error): void {
    this.log('error', 'Pipeline error:', error);
    this.lastError = error.message;
    this.currentPhase = 'error';
    this.emit('error', error);
    this.emitStatusUpdate();
  }

  /**
   * Emit status update
   */
  private emitStatusUpdate(): void {
    const status = this.getStatus();
    this.emit('status:update', status);
  }

  /**
   * Get current pipeline status
   */
  getStatus(): PipelineStatus {
    return {
      isRunning: this.isRunning,
      phase: this.currentPhase,
      streamId: this.config.streamId,
      sourceUrl: this.config.sourceUrl,
      stats: this.stats,
      lastError: this.lastError,
      startTime: this.startTime,
      uptime: this.startTime ? Math.floor((Date.now() - this.startTime.getTime()) / 1000) : 0,
    };
  }

  // Typed event emitter methods
  on<K extends keyof PipelineOrchestratorEvents>(
    event: K,
    listener: PipelineOrchestratorEvents[K]
  ): this {
    return super.on(event, listener);
  }

  emit<K extends keyof PipelineOrchestratorEvents>(
    event: K,
    ...args: Parameters<PipelineOrchestratorEvents[K]>
  ): boolean {
    return super.emit(event, ...args);
  }
}

