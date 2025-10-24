/**
 * Buffer manager for accumulating segments into 30-second batches
 */
import { SegmentMetadata, SegmentBatch } from '../types/index.js';
import { getLogger } from '../utils/logger.js';

let logger: ReturnType<typeof getLogger> | null = null;

/**
 * Buffer manager service
 */
export class BufferManager {
  private bufferDurationSeconds: number;
  private currentBatch: SegmentMetadata[];
  private currentDuration: number;
  private batchCounter: number;

  constructor(bufferDurationSeconds: number = 30) {
    this.bufferDurationSeconds = bufferDurationSeconds;
    this.currentBatch = [];
    this.currentDuration = 0;
    this.batchCounter = 0;

    // Lazy initialize logger
    if (!logger) {
      try {
        logger = getLogger().child({ context: 'BufferManager' });
      } catch {
        // Logger not initialized yet
        logger = null;
      }
    }

    this.log('info', `BufferManager initialized with ${bufferDurationSeconds}s buffer`);
  }

  private log(level: 'debug' | 'info' | 'warn' | 'error', message: string, ...args: unknown[]): void {
    if (logger) {
      logger[level](message, ...args);
    }
  }

  /**
   * Add a segment to the buffer
   * @returns SegmentBatch if buffer is full, null otherwise
   */
  addSegment(segment: SegmentMetadata): SegmentBatch | null {
    this.currentBatch.push(segment);
    this.currentDuration += segment.duration;

    this.log(
      'debug',
      `Added segment ${segment.id}, current duration: ${this.currentDuration.toFixed(2)}s`
    );

    // Check if batch is ready
    if (this.currentDuration >= this.bufferDurationSeconds) {
      return this.createBatch();
    }

    return null;
  }

  /**
   * Force create a batch with current segments (even if not full)
   */
  flush(): SegmentBatch | null {
    if (this.currentBatch.length === 0) {
      return null;
    }

    this.log('info', 'Flushing buffer to create batch');
    return this.createBatch();
  }

  /**
   * Create a batch from current buffer and reset
   */
  private createBatch(): SegmentBatch {
    const batch: SegmentBatch = {
      batchNumber: this.batchCounter++,
      segments: [...this.currentBatch],
      totalDuration: this.currentDuration,
      totalSize: this.currentBatch.reduce((sum, seg) => sum + seg.size, 0),
      timestamp: new Date(),
    };

    this.log(
      'info',
      `Created batch ${batch.batchNumber}: ${batch.segments.length} segments, ` +
      `${batch.totalDuration.toFixed(2)}s, ${(batch.totalSize / 1024 / 1024).toFixed(2)} MB`
    );

    // Reset buffer
    this.currentBatch = [];
    this.currentDuration = 0;

    return batch;
  }

  /**
   * Get current buffer status
   */
  getStatus(): {
    segmentCount: number;
    currentDuration: number;
    progress: number;
    nextBatchNumber: number;
  } {
    return {
      segmentCount: this.currentBatch.length,
      currentDuration: this.currentDuration,
      progress: (this.currentDuration / this.bufferDurationSeconds) * 100,
      nextBatchNumber: this.batchCounter,
    };
  }

  /**
   * Reset the buffer
   */
  reset(): void {
    this.log('info', 'Resetting buffer');
    this.currentBatch = [];
    this.currentDuration = 0;
    this.batchCounter = 0;
  }

  /**
   * Get current buffer size in bytes
   */
  getCurrentSize(): number {
    return this.currentBatch.reduce((sum, seg) => sum + seg.size, 0);
  }

  /**
   * Check if buffer is empty
   */
  isEmpty(): boolean {
    return this.currentBatch.length === 0;
  }

  /**
   * Check if buffer is ready (duration threshold met)
   */
  isReady(): boolean {
    return this.currentDuration >= this.bufferDurationSeconds;
  }
}

