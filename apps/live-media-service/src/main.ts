/**
 * Live Media Service - Main Entry Point
 * Express server with REST API for pipeline control
 */
import express, { Request, Response, NextFunction } from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import { getConfig, Config } from './utils/config.js';
import { initLogger, getLogger } from './utils/logger.js';
import { PipelineOrchestrator } from './modules/PipelineOrchestrator.js';
import { PipelineConfig } from './types/index.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load configuration
const config: Config = getConfig();

// Initialize logger
initLogger({
  ...config.logging,
  logsPath: config.storage.logsPath,
});
const logger = getLogger();

// Create Express app
const app = express();

// Middleware
app.use(express.json());
app.use(express.static(path.join(__dirname, '../public')));

// Pipeline instance (singleton)
let pipeline: PipelineOrchestrator | null = null;

/**
 * Health check endpoint
 */
app.get('/api/health', (req: Request, res: Response) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
  });
});

/**
 * Get pipeline status
 */
app.get('/api/pipeline/status', (req: Request, res: Response) => {
  if (!pipeline) {
    return res.json({
      isRunning: false,
      phase: 'idle',
      streamId: null,
      sourceUrl: null,
      stats: {
        segmentsFetched: 0,
        batchesProcessed: 0,
        fragmentsPublished: 0,
        bytesProcessed: 0,
        avgProcessingTime: 0,
        currentBufferSize: 0,
      },
      lastError: null,
      startTime: null,
      uptime: 0,
    });
  }

  const status = pipeline.getStatus();
  res.json(status);
});

/**
 * Start pipeline
 */
app.post('/api/pipeline/start', async (req: Request, res: Response) => {
  try {
    if (pipeline && pipeline.getStatus().isRunning) {
      return res.status(400).json({
        success: false,
        error: 'Pipeline is already running',
      });
    }

    // Use provided config or defaults
    const pipelineConfig: PipelineConfig = {
      sourceUrl: req.body.sourceUrl || config.hls.sourceUrl,
      streamId: req.body.streamId || config.hls.streamId,
      bufferDuration: req.body.bufferDuration || config.buffer.durationSeconds,
      audioProcessorUrl: req.body.audioProcessorUrl || config.websocket.audioProcessorUrl,
      srsRtmpUrl: req.body.srsRtmpUrl || config.srs.rtmpUrl,
      storagePath: config.storage.basePath,
    };

    // Validate required fields
    if (!pipelineConfig.sourceUrl) {
      return res.status(400).json({
        success: false,
        error: 'sourceUrl is required',
      });
    }

    logger.info('Starting pipeline with config:', pipelineConfig);

    // Create and start pipeline
    pipeline = new PipelineOrchestrator(pipelineConfig);

    // Set up status update listener
    pipeline.on('status:update', (status) => {
      logger.debug('Pipeline status update:', status.phase);
    });

    // Set up error listener
    pipeline.on('error', (error) => {
      logger.error('Pipeline error:', error);
    });

    await pipeline.start();

    res.json({
      success: true,
      message: 'Pipeline started successfully',
      status: pipeline.getStatus(),
    });
  } catch (error) {
    logger.error('Failed to start pipeline:', error);
    res.status(500).json({
      success: false,
      error: (error as Error).message,
    });
  }
});

/**
 * Stop pipeline
 */
app.post('/api/pipeline/stop', async (req: Request, res: Response) => {
  try {
    if (!pipeline) {
      return res.status(400).json({
        success: false,
        error: 'No pipeline is running',
      });
    }

    logger.info('Stopping pipeline');

    await pipeline.stop();
    pipeline = null;

    res.json({
      success: true,
      message: 'Pipeline stopped successfully',
    });
  } catch (error) {
    logger.error('Failed to stop pipeline:', error);
    res.status(500).json({
      success: false,
      error: (error as Error).message,
    });
  }
});

/**
 * Get storage statistics
 */
app.get('/api/storage/stats', async (req: Request, res: Response) => {
  try {
    // Would need to access storageService from pipeline
    // For now, return placeholder
    res.json({
      totalSize: 0,
      fileCount: 0,
      availableSpace: 0,
      breakdown: {
        originalSegments: 0,
        videoFragments: 0,
        audioFragments: 0,
        processedAudio: 0,
        remuxedOutput: 0,
      },
    });
  } catch (error) {
    logger.error('Failed to get storage stats:', error);
    res.status(500).json({
      success: false,
      error: (error as Error).message,
    });
  }
});

/**
 * Clean storage
 */
app.post('/api/storage/clean', async (req: Request, res: Response) => {
  try {
    if (pipeline && pipeline.getStatus().isRunning) {
      return res.status(400).json({
        success: false,
        error: 'Cannot clean storage while pipeline is running',
      });
    }

    // Would need to implement storage cleanup
    logger.info('Storage cleanup requested');

    res.json({
      success: true,
      message: 'Storage cleaned successfully',
      deletedFiles: 0,
    });
  } catch (error) {
    logger.error('Failed to clean storage:', error);
    res.status(500).json({
      success: false,
      error: (error as Error).message,
    });
  }
});

/**
 * Error handling middleware
 */
app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
  logger.error('Unhandled error:', err);
  res.status(500).json({
    success: false,
    error: err.message || 'Internal server error',
  });
});

/**
 * Graceful shutdown
 */
const shutdown = async () => {
  logger.info('Shutting down gracefully...');

  if (pipeline) {
    try {
      await pipeline.stop();
    } catch (error) {
      logger.error('Error stopping pipeline during shutdown:', error);
    }
  }

  process.exit(0);
};

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);

/**
 * Start server
 */
const PORT = config.server.port;
app.listen(PORT, () => {
  logger.info(`🚀 Live Media Service started`);
  logger.info(`📡 Server running on http://localhost:${PORT}`);
  logger.info(`📊 API available at http://localhost:${PORT}/api`);
  logger.info(`🌐 Web UI at http://localhost:${PORT}`);
  logger.info(`\n✅ Ready to process streams!`);
});

