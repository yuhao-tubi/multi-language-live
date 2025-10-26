/**
 * Configuration loader and validator
 */
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load environment variables
dotenv.config({ path: path.resolve(__dirname, '../../.env') });

/**
 * Application configuration
 */
export interface Config {
  server: {
    port: number;
    nodeEnv: string;
  };
  hls: {
    sourceUrl: string;
    streamId: string;
  };
  buffer: {
    durationSeconds: number;
    maxSizeMB: number;
  };
  websocket: {
    audioProcessorUrl: string;
    reconnectAttempts: number;
    reconnectDelayMs: number;
  };
  srs: {
    srtUrl: string;
    httpApi: string;
    hlsOutput: string;
  };
  storage: {
    basePath: string;
    originalStreamPath: string;
    processedFragmentsPath: string;
    logsPath: string;
  };
  cleanup: {
    autoCleanupEnabled: boolean;
    intervalHours: number;
    maxAgeHours: number;
  };
  ffmpeg: {
    path: string;
    logLevel: string;
  };
  streaming: {
    chunkSizeKB: number;
    stdinBufferSizeMB: number;
    maxSegmentsToKeep: number;
    enableCleanup: boolean;
  };
  logging: {
    level: string;
    format: 'json' | 'simple';
    toFile: boolean;
    toConsole: boolean;
    moduleFilter?: string[];
  };
}

/**
 * Load configuration from environment variables
 */
export function loadConfig(): Config {
  return {
    server: {
      port: parseInt(process.env.PORT || '3000', 10),
      nodeEnv: process.env.NODE_ENV || 'development',
    },
    hls: {
      sourceUrl: process.env.SOURCE_URL || '',
      streamId: process.env.STREAM_ID || 'default-stream',
    },
    buffer: {
      durationSeconds: parseInt(process.env.BUFFER_DURATION_SECONDS || '10', 10),
      maxSizeMB: parseInt(process.env.MAX_BUFFER_SIZE_MB || '500', 10),
    },
    websocket: {
      audioProcessorUrl: process.env.AUDIO_PROCESSOR_URL || 'http://localhost:5000',
      reconnectAttempts: parseInt(process.env.SOCKET_RECONNECT_ATTEMPTS || '5', 10),
      reconnectDelayMs: parseInt(process.env.SOCKET_RECONNECT_DELAY_MS || '2000', 10),
    },
    srs: {
      srtUrl: process.env.SRS_SRT_URL || 'srt://localhost:10080',
      httpApi: process.env.SRS_HTTP_API || 'http://localhost:1985/api/v1',
      hlsOutput: process.env.SRS_HLS_OUTPUT || 'http://localhost:8080',
    },
    storage: {
      basePath: process.env.STORAGE_BASE_PATH || './storage',
      originalStreamPath: process.env.ORIGINAL_STREAM_PATH || './storage/original_stream',
      processedFragmentsPath: process.env.PROCESSED_FRAGMENTS_PATH || './storage/processed_fragments',
      logsPath: process.env.LOGS_PATH || './storage/logs',
    },
    cleanup: {
      autoCleanupEnabled: process.env.AUTO_CLEANUP_ENABLED === 'true',
      intervalHours: parseInt(process.env.CLEANUP_INTERVAL_HOURS || '24', 10),
      maxAgeHours: parseInt(process.env.MAX_STORAGE_AGE_HOURS || '48', 10),
    },
    ffmpeg: {
      path: process.env.FFMPEG_PATH || '/usr/local/bin/ffmpeg',
      logLevel: process.env.FFMPEG_LOG_LEVEL || 'error',
    },
    streaming: {
      chunkSizeKB: parseInt(process.env.CHUNK_SIZE_KB || '1024', 10),
      stdinBufferSizeMB: parseInt(process.env.STDIN_BUFFER_SIZE_MB || '2', 10),
      maxSegmentsToKeep: parseInt(process.env.MAX_SEGMENTS_TO_KEEP || '3', 10),
      enableCleanup: process.env.ENABLE_SEGMENT_CLEANUP !== 'false',
    },
    logging: {
      level: process.env.LOG_LEVEL || 'info',
      format: (process.env.LOG_FORMAT === 'json' ? 'json' : 'simple') as 'json' | 'simple',
      toFile: process.env.LOG_TO_FILE !== 'false',
      toConsole: process.env.LOG_TO_CONSOLE !== 'false',
      moduleFilter: process.env.LOG_MODULE_FILTER 
        ? process.env.LOG_MODULE_FILTER.split(',').map(m => m.trim()).filter(m => m.length > 0)
        : undefined,
    },
  };
}

/**
 * Validate configuration
 * @throws Error if configuration is invalid
 */
export function validateConfig(config: Config): void {
  const errors: string[] = [];

  // Validate required fields
  if (!config.hls.sourceUrl) {
    errors.push('SOURCE_URL is required');
  }

  if (!config.hls.streamId) {
    errors.push('STREAM_ID is required');
  }

  if (config.buffer.durationSeconds <= 0) {
    errors.push('BUFFER_DURATION_SECONDS must be positive');
  }

  if (config.server.port <= 0 || config.server.port > 65535) {
    errors.push('PORT must be between 1 and 65535');
  }

  if (errors.length > 0) {
    throw new Error(`Configuration validation failed:\n${errors.join('\n')}`);
  }
}

/**
 * Get validated configuration
 */
export function getConfig(): Config {
  const config = loadConfig();
  validateConfig(config);
  return config;
}

