#!/usr/bin/env node

import express, { Request, Response } from 'express';
import { MultiProcessPipeline } from './MultiProcessPipeline.js';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

/**
 * Web-Based Multi-Process Pipeline Server
 * Provides REST API and web UI for controlling the HLS audio pipeline
 */

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Global pipeline instance
let pipeline: MultiProcessPipeline | null = null;
let isShuttingDown = false;

// Create Express app
const app = express();

// Middleware
app.use(express.json());
app.use(express.static(join(__dirname, '..')));

/**
 * POST /api/start
 * Start the pipeline with provided URLs
 * Body: { sourceUrl: string, srsRtmpUrl: string, sampleRate?: number, channels?: number }
 */
app.post('/api/start', async (req: Request, res: Response) => {
  try {
    const { sourceUrl, srsRtmpUrl, sampleRate = 48000, channels = 2 } = req.body;

    // Validate input
    if (!sourceUrl || typeof sourceUrl !== 'string') {
      return res.status(400).json({ 
        success: false, 
        error: 'sourceUrl is required and must be a string' 
      });
    }

    if (!srsRtmpUrl || typeof srsRtmpUrl !== 'string') {
      return res.status(400).json({ 
        success: false, 
        error: 'srsRtmpUrl is required and must be a string' 
      });
    }

    // Check if pipeline is already running
    if (pipeline && pipeline.getStatus().isRunning) {
      return res.status(400).json({ 
        success: false, 
        error: 'Pipeline is already running. Stop it first.' 
      });
    }

    // Create and start new pipeline
    console.log('[API] Starting pipeline...');
    console.log(`[API]   Source: ${sourceUrl}`);
    console.log(`[API]   Output: ${srsRtmpUrl}`);

    pipeline = new MultiProcessPipeline(sourceUrl, srsRtmpUrl, sampleRate, channels);
    await pipeline.start();

    res.json({ 
      success: true, 
      message: 'Pipeline started successfully',
      config: pipeline.getConfig()
    });
  } catch (error) {
    console.error('[API] Error starting pipeline:', error);
    
    // Clean up on error
    if (pipeline) {
      try {
        await pipeline.stop();
      } catch (stopError) {
        console.error('[API] Error stopping pipeline after start failure:', stopError);
      }
      pipeline = null;
    }

    res.status(500).json({ 
      success: false, 
      error: error instanceof Error ? error.message : 'Unknown error occurred' 
    });
  }
});

/**
 * POST /api/stop
 * Stop the running pipeline
 */
app.post('/api/stop', async (req: Request, res: Response) => {
  try {
    if (!pipeline) {
      return res.status(400).json({ 
        success: false, 
        error: 'No pipeline is running' 
      });
    }

    console.log('[API] Stopping pipeline...');
    await pipeline.stop();
    pipeline = null;

    res.json({ 
      success: true, 
      message: 'Pipeline stopped successfully' 
    });
  } catch (error) {
    console.error('[API] Error stopping pipeline:', error);
    res.status(500).json({ 
      success: false, 
      error: error instanceof Error ? error.message : 'Unknown error occurred' 
    });
  }
});

/**
 * GET /api/status
 * Get current pipeline status
 */
app.get('/api/status', (req: Request, res: Response) => {
  if (!pipeline) {
    return res.json({
      isRunning: false,
      config: null,
      processes: {
        demux: false,
        decode: false,
        encode: false,
        remux: false
      }
    });
  }

  const status = pipeline.getStatus();
  const config = pipeline.getConfig();

  res.json({
    isRunning: status.isRunning,
    config: config,
    processes: status.processes
  });
});

/**
 * Graceful shutdown handler
 */
const shutdown = async (signal: string) => {
  if (isShuttingDown) {
    console.log('\n[SERVER] Force exit...');
    process.exit(1);
  }

  isShuttingDown = true;
  console.log(`\n[SERVER] Received ${signal}, shutting down gracefully...`);
  
  try {
    if (pipeline) {
      await pipeline.stop();
      pipeline = null;
    }
    console.log('[SERVER] ✓ Shutdown complete');
    process.exit(0);
  } catch (error) {
    console.error('[SERVER] Error during shutdown:', error);
    process.exit(1);
  }
};

// Register signal handlers
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));

// Handle uncaught errors
process.on('uncaughtException', (error) => {
  console.error('[SERVER] Uncaught exception:', error);
  shutdown('UNCAUGHT_EXCEPTION').catch(() => process.exit(1));
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('[SERVER] Unhandled rejection at:', promise, 'reason:', reason);
  shutdown('UNHANDLED_REJECTION').catch(() => process.exit(1));
});

/**
 * Start the server with port fallback
 */
const startServer = async (startPort: number = 3000, maxAttempts: number = 10): Promise<void> => {
  let currentPort = startPort;
  let attempts = 0;

  while (attempts < maxAttempts) {
    try {
      await new Promise<void>((resolve, reject) => {
        const server = app.listen(currentPort, () => {
          console.log('╔════════════════════════════════════════════════════════════╗');
          console.log('║  Multi-Process HLS Audio Pipeline Web Server              ║');
          console.log('╚════════════════════════════════════════════════════════════╝');
          console.log('');
          console.log(`🌐 Server running at: http://localhost:${currentPort}`);
          console.log('');
          console.log('📖 API Endpoints:');
          console.log(`   POST http://localhost:${currentPort}/api/start`);
          console.log(`   POST http://localhost:${currentPort}/api/stop`);
          console.log(`   GET  http://localhost:${currentPort}/api/status`);
          console.log('');
          console.log('🎨 Web UI:');
          console.log(`   Open http://localhost:${currentPort}/ in your browser`);
          console.log('');
          console.log('Press Ctrl+C to stop the server');
          console.log('');
          resolve();
        }).on('error', (err: NodeJS.ErrnoException) => {
          if (err.code === 'EADDRINUSE') {
            reject(err);
          } else {
            console.error('[SERVER] Server error:', err);
            process.exit(1);
          }
        });
      });

      // Successfully started
      return;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'EADDRINUSE') {
        console.log(`[SERVER] Port ${currentPort} is in use, trying ${currentPort + 1}...`);
        currentPort++;
        attempts++;
      } else {
        throw error;
      }
    }
  }

  console.error(`[SERVER] Failed to find an available port after ${maxAttempts} attempts`);
  process.exit(1);
};

// Start the server
startServer().catch((error) => {
  console.error('[SERVER] Failed to start server:', error);
  process.exit(1);
});
