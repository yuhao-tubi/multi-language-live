/**
 * Core type definitions for Live Media Service
 */

/**
 * Segment metadata from HLS stream
 */
export interface SegmentMetadata {
  /** Unique segment identifier */
  id: string;
  /** Path to segment file on disk */
  path: string;
  /** Segment size in bytes */
  size: number;
  /** Duration in seconds */
  duration: number;
  /** Timestamp when segment was fetched */
  timestamp: Date;
  /** Sequence number in stream */
  sequence: number;
}

/**
 * Batch of segments ready for processing
 */
export interface SegmentBatch {
  /** Batch number (incrementing) */
  batchNumber: number;
  /** Array of segment metadata */
  segments: SegmentMetadata[];
  /** Total duration of batch in seconds */
  totalDuration: number;
  /** Total size in bytes */
  totalSize: number;
  /** Timestamp when batch was created */
  timestamp: Date;
}

/**
 * Demuxed output from FFmpeg
 */
export interface DemuxedOutput {
  /** Batch number */
  batchNumber: number;
  /** Path to video FMP4 file */
  videoPath: string;
  /** Path to audio FMP4 file */
  audioPath: string;
  /** Video file size in bytes */
  videoSize: number;
  /** Audio file size in bytes */
  audioSize: number;
  /** Timestamp of demux operation */
  timestamp: Date;
}

/**
 * Processed audio result
 */
export interface ProcessedAudio {
  /** Batch number */
  batchNumber: number;
  /** Path to processed audio file */
  audioPath: string;
  /** File size in bytes */
  size: number;
  /** Processing timestamp */
  timestamp: Date;
  /** Optional metadata from processor */
  metadata?: Record<string, unknown>;
}

/**
 * Remuxed output
 */
export interface RemuxedOutput {
  /** Batch number */
  batchNumber: number;
  /** Path to output FMP4 file */
  outputPath: string;
  /** File size in bytes */
  size: number;
  /** Timestamp of remux operation */
  timestamp: Date;
}

/**
 * Pipeline status
 */
export interface PipelineStatus {
  /** Is pipeline currently running */
  isRunning: boolean;
  /** Current phase */
  phase: 'idle' | 'fetching' | 'processing' | 'publishing' | 'error';
  /** Stream ID being processed */
  streamId: string | null;
  /** Source URL */
  sourceUrl: string | null;
  /** Statistics */
  stats: PipelineStats;
  /** Last error if any */
  lastError: string | null;
  /** Start time */
  startTime: Date | null;
  /** Uptime in seconds */
  uptime: number;
}

/**
 * Pipeline statistics
 */
export interface PipelineStats {
  /** Total segments fetched */
  segmentsFetched: number;
  /** Total batches processed */
  batchesProcessed: number;
  /** Total fragments published */
  fragmentsPublished: number;
  /** Total bytes processed */
  bytesProcessed: number;
  /** Average processing time per batch (ms) */
  avgProcessingTime: number;
  /** Current buffer size (seconds) */
  currentBufferSize: number;
}

/**
 * Configuration for pipeline
 */
export interface PipelineConfig {
  /** Source HLS URL */
  sourceUrl: string;
  /** Stream identifier */
  streamId: string;
  /** Buffer duration in seconds */
  bufferDuration: number;
  /** Audio processor WebSocket URL */
  audioProcessorUrl: string;
  /** SRS SRT URL */
  srtUrl: string;
  /** Storage base path */
  storagePath: string;
}

/**
 * Storage statistics
 */
export interface StorageStats {
  /** Total storage used (bytes) */
  totalSize: number;
  /** Number of files */
  fileCount: number;
  /** Breakdown by type */
  breakdown: {
    originalSegments: number;
    videoFragments: number;
    audioFragments: number;
    processedAudio: number;
    remuxedOutput: number;
  };
  /** Available disk space (bytes) */
  availableSpace: number;
}

