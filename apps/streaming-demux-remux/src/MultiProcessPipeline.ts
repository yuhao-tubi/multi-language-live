import { ChildProcess } from 'child_process';
import { Readable } from 'stream';
import * as M3U8Parser from 'm3u8-parser';
import m3u8stream from 'm3u8stream';
import { createDemuxProcess } from './processes/DemuxProcess.js';
import { createDecodeProcess } from './processes/DecodeProcess.js';
import { createEncodeProcess } from './processes/EncodeProcess.js';
import { createRemuxProcess } from './processes/RemuxProcess.js';
import { CustomAudioTransform } from './transforms/AudioProcessor.js';

/**
 * Multi-Process Pipeline Orchestrator
 * Manages the entire stream processing pipeline from HLS input to SRS output
 */

interface ProcessCollection {
  demux: ChildProcess | null;
  decode: ChildProcess | null;
  encode: ChildProcess | null;
  remux: ChildProcess | null;
}

export class MultiProcessPipeline {
  private sourceUrl: string;
  private srsRtmpUrl: string;
  private sampleRate: number;
  private channels: number;
  private processes: ProcessCollection;
  private inputStream: Readable | null = null;
  private audioTransform: CustomAudioTransform | null = null;
  private isRunning: boolean = false;

  constructor(
    sourceUrl: string, 
    srsRtmpUrl: string, 
    sampleRate: number = 48000, 
    channels: number = 2
  ) {
    this.sourceUrl = sourceUrl;
    this.srsRtmpUrl = srsRtmpUrl;
    this.sampleRate = sampleRate;
    this.channels = channels;
    this.processes = {
      demux: null,
      decode: null,
      encode: null,
      remux: null
    };
  }

  /**
   * Start the multi-process pipeline
   */
  async start(): Promise<void> {
    if (this.isRunning) {
      console.warn('[PIPELINE] Already running');
      return;
    }

    console.log('[PIPELINE] Starting multi-process audio pipeline...');
    console.log(`[PIPELINE] Source: ${this.sourceUrl}`);
    console.log(`[PIPELINE] Output: ${this.srsRtmpUrl}`);
    console.log(`[PIPELINE] Audio config: ${this.sampleRate}Hz, ${this.channels} channels`);

    try {
      // Step 1: Fetch and parse HLS manifest
      console.log('[PIPELINE] Fetching HLS manifest...');
      const manifestResponse = await fetch(this.sourceUrl);
      if (!manifestResponse.ok) {
        throw new Error(`Failed to fetch manifest: ${manifestResponse.statusText}`);
      }
      const manifestText = await manifestResponse.text();

      // Step 2: Parse manifest
      const parser = new M3U8Parser.Parser();
      parser.push(manifestText);
      parser.end();

      const manifest = parser.manifest;

      // Step 3: Select variant playlist
      if (!manifest.playlists || manifest.playlists.length === 0) {
        throw new Error('No playlists found in manifest');
      }

      // Select first variant (or could implement quality selection logic)
      const selectedVariant = manifest.playlists[0];
      console.log(`[PIPELINE] Selected variant: ${selectedVariant.attributes?.RESOLUTION?.width || 'unknown'}x${selectedVariant.attributes?.RESOLUTION?.height || 'unknown'} @ ${selectedVariant.attributes?.BANDWIDTH || 'unknown'} bps`);

      // Resolve media playlist URL
      const mediaPlaylistUrl = this._resolveUrl(this.sourceUrl, selectedVariant.uri);
      console.log(`[PIPELINE] Media playlist: ${mediaPlaylistUrl}`);

      // Step 4: Create HLS segment stream
      console.log('[PIPELINE] Creating HLS segment stream...');
      this.inputStream = m3u8stream(mediaPlaylistUrl, {
        chunkReadahead: 3
      });

      // Step 5: Create Process 1 (Demux)
      console.log('[PIPELINE] Starting demux process...');
      if (!this.inputStream) {
        throw new Error('Input stream not initialized');
      }
      const demuxResult = createDemuxProcess(this.inputStream);
      this.processes.demux = demuxResult.process;

      // Step 6: Create Process 2 (Decode) - only for audio
      console.log('[PIPELINE] Starting decode process...');
      const decodeResult = createDecodeProcess(
        demuxResult.audioOut, 
        this.sampleRate, 
        this.channels
      );
      this.processes.decode = decodeResult.process;

      // Step 7: Create custom audio transform
      console.log('[PIPELINE] Creating audio transform...');
      this.audioTransform = new CustomAudioTransform(this.sampleRate, this.channels);

      // Step 8: Create Process 3 (Encode)
      console.log('[PIPELINE] Starting encode process...');
      const processedPcm = decodeResult.pcmOut.pipe(this.audioTransform);
      const encodeResult = createEncodeProcess(
        processedPcm, 
        this.sampleRate, 
        this.channels
      );
      this.processes.encode = encodeResult.process;

      // Step 9: Create Process 4 (Remux) - combines video + processed audio
      console.log('[PIPELINE] Starting remux process...');
      const remuxResult = createRemuxProcess(
        demuxResult.videoOut, 
        encodeResult.aacOut, 
        this.srsRtmpUrl
      );
      this.processes.remux = remuxResult.process;

      // Step 10: Set up error handlers
      this._setupErrorHandlers();

      this.isRunning = true;
      console.log('[PIPELINE] ✓ Pipeline started successfully');
      console.log('[PIPELINE] Streaming to SRS...');
    } catch (error) {
      console.error('[PIPELINE] Failed to start:', error);
      await this.stop();
      throw error;
    }
  }

  /**
   * Stop the pipeline gracefully
   */
  async stop(): Promise<void> {
    if (!this.isRunning) {
      console.log('[PIPELINE] Not running');
      return;
    }

    console.log('[PIPELINE] Stopping pipeline...');
    this.isRunning = false;

    // Stop processes in reverse order
    const processOrder: (keyof ProcessCollection)[] = ['remux', 'encode', 'decode', 'demux'];
    
    for (const processName of processOrder) {
      const process = this.processes[processName];
      if (process && !process.killed) {
        console.log(`[PIPELINE] Stopping ${processName}...`);
        process.kill('SIGTERM');
        
        // Wait a bit for graceful shutdown
        await new Promise(resolve => setTimeout(resolve, 500));
        
        // Force kill if still alive
        if (!process.killed) {
          console.log(`[PIPELINE] Force killing ${processName}...`);
          process.kill('SIGKILL');
        }
      }
      this.processes[processName] = null;
    }

    // Clean up stream references
    if (this.inputStream) {
      this.inputStream.destroy();
      this.inputStream = null;
    }

    this.audioTransform = null;

    console.log('[PIPELINE] ✓ Pipeline stopped');
  }

  /**
   * Set up error handlers for all processes and streams
   */
  private _setupErrorHandlers(): void {
    // Monitor all process exits
    Object.entries(this.processes).forEach(([name, proc]) => {
      if (!proc) return;

      proc.on('exit', (code: number | null, signal: NodeJS.Signals | null) => {
        if (code !== 0 && code !== null) {
          console.error(`[PIPELINE] ${name} exited unexpectedly: code=${code}, signal=${signal}`);
          // Kill entire pipeline on failure
          this.stop().catch((err: Error) => 
            console.error('[PIPELINE] Error during emergency shutdown:', err)
          );
        }
      });

      proc.on('error', (err: Error) => {
        console.error(`[PIPELINE] ${name} error:`, err);
        this.stop().catch((stopErr: Error) => 
          console.error('[PIPELINE] Error during emergency shutdown:', stopErr)
        );
      });
    });

    // Handle input stream errors
    if (this.inputStream) {
      this.inputStream.on('error', (err) => {
        console.error('[PIPELINE] HLS Input stream error:', err);
        this.stop().catch(stopErr => 
          console.error('[PIPELINE] Error during emergency shutdown:', stopErr)
        );
      });
    }

    // Handle audio transform errors
    if (this.audioTransform) {
      this.audioTransform.on('error', (err) => {
        console.error('[PIPELINE] Audio transform error:', err);
        this.stop().catch(stopErr => 
          console.error('[PIPELINE] Error during emergency shutdown:', stopErr)
        );
      });
    }
  }

  /**
   * Resolve relative URLs against base URL
   */
  private _resolveUrl(baseUrl: string, relativeUrl: string): string {
    // If already absolute, return as-is
    if (relativeUrl.startsWith('http://') || relativeUrl.startsWith('https://')) {
      return relativeUrl;
    }

    // Parse base URL
    const base = new URL(baseUrl);
    
    // Handle relative paths
    if (relativeUrl.startsWith('/')) {
      // Absolute path relative to origin
      return `${base.origin}${relativeUrl}`;
    } else {
      // Relative path
      const basePath = base.pathname.substring(0, base.pathname.lastIndexOf('/') + 1);
      return `${base.origin}${basePath}${relativeUrl}`;
    }
  }

  /**
   * Get pipeline status
   */
  getStatus(): { isRunning: boolean; processes: Record<string, boolean> } {
    return {
      isRunning: this.isRunning,
      processes: {
        demux: this.processes.demux !== null && !this.processes.demux.killed,
        decode: this.processes.decode !== null && !this.processes.decode.killed,
        encode: this.processes.encode !== null && !this.processes.encode.killed,
        remux: this.processes.remux !== null && !this.processes.remux.killed
      }
    };
  }

  /**
   * Get current configuration
   */
  getConfig(): { sourceUrl: string; srsRtmpUrl: string; sampleRate: number; channels: number } {
    return {
      sourceUrl: this.sourceUrl,
      srsRtmpUrl: this.srsRtmpUrl,
      sampleRate: this.sampleRate,
      channels: this.channels
    };
  }
}

