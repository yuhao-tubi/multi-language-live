/**
 * WebSocket protocol types for audio processor communication
 * Based on mock-media-service protocol
 */

/**
 * Fragment metadata sent to audio processor
 */
export interface FragmentMetadata {
  /** Unique fragment ID (e.g., "stream-1_batch-5") */
  id: string;
  /** Stream identifier */
  streamId: string;
  /** Batch number */
  batchNumber: number;
  /** Content type (always audio/mp4 for FMP4) */
  contentType: string;
  /** Size in bytes */
  size: number;
  /** Duration in seconds */
  duration: number;
  /** Timestamp */
  timestamp: string;
  /** Optional metadata */
  metadata?: Record<string, unknown>;
}

/**
 * Event sent when fragment data is transmitted
 */
export interface FragmentDataEvent {
  /** Fragment metadata */
  fragment: FragmentMetadata;
  /** Audio data as Buffer (binary) */
  data: Buffer;
}

/**
 * Event received when fragment is processed
 */
export interface FragmentProcessedEvent {
  /** Original fragment metadata */
  fragment: FragmentMetadata;
  /** Processed audio data as Buffer (binary) */
  data: Buffer;
  /** Optional processing metadata */
  metadata?: {
    /** Processing duration in ms */
    processingTime?: number;
    /** Language detected/used */
    language?: string;
    /** Any warnings */
    warnings?: string[];
    /** Custom fields */
    [key: string]: unknown;
  };
}

/**
 * Error event from audio processor
 */
export interface FragmentErrorEvent {
  /** Fragment that failed */
  fragment: FragmentMetadata;
  /** Error message */
  error: string;
  /** Error code */
  code?: string;
  /** Additional error details */
  details?: Record<string, unknown>;
}

/**
 * WebSocket event types
 */
export type SocketEventType =
  | 'fragment:data'       // Client sends audio data
  | 'fragment:processed'  // Server sends processed audio
  | 'fragment:error'      // Server sends error
  | 'fragment:status'     // Status updates
  | 'connect'             // Connection established
  | 'disconnect'          // Connection lost
  | 'error';              // Connection error

