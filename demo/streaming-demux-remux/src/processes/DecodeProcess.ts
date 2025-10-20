import { spawn, ChildProcess } from 'child_process';
import { Readable } from 'stream';

/**
 * Process 2: Audio Decoder
 * Decodes compressed audio to raw PCM for Node.js processing
 * 
 * Input: Compressed audio in Nut format (stdin)
 * Output: Raw PCM audio (stdout) - s16le format
 */

export interface DecodeResult {
  process: ChildProcess;
  pcmOut: Readable;
}

export function createDecodeProcess(
  audioStream: Readable, 
  sampleRate: number, 
  channels: number
): DecodeResult {
  const args = [
    '-f', 'nut',                      // Input is Nut container with audio
    '-i', 'pipe:0',                   // Audio from demux process
    '-vn',                            // No video
    '-f', 's16le',                    // Signed 16-bit little-endian PCM
    '-acodec', 'pcm_s16le',           // PCM codec
    '-ar', sampleRate.toString(),     // Sample rate (e.g., 48000)
    '-ac', channels.toString(),       // Channels (e.g., 2 for stereo)
    'pipe:1'                          // PCM output to stdout
  ];

  const ffmpegProcess = spawn('ffmpeg', args, {
    stdio: ['pipe', 'pipe', 'pipe']
  });

  // Pipe compressed audio to FFmpeg stdin
  audioStream.pipe(ffmpegProcess.stdin!);

  // Get PCM output stream
  const pcmOut = ffmpegProcess.stdout as Readable;

  // Monitor stderr for errors
  ffmpegProcess.stderr!.on('data', (data: Buffer) => {
    console.log(`[DECODE]: ${data.toString()}`);
  });

  ffmpegProcess.on('exit', (code, signal) => {
    console.log(`[DECODE] Process exited with code ${code} and signal ${signal}`);
  });

  ffmpegProcess.on('error', (err) => {
    console.error('[DECODE] Process error:', err);
  });

  return {
    process: ffmpegProcess,
    pcmOut
  };
}

