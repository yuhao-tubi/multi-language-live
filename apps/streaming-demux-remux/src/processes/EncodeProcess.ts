import { spawn, ChildProcess } from 'child_process';
import { Readable } from 'stream';

/**
 * Process 3: Audio Re-encoder
 * Re-encodes PCM audio to AAC
 * 
 * Input: Raw PCM audio (stdin)
 * Output: AAC encoded audio in Nut format (stdout)
 */

export interface EncodeResult {
  process: ChildProcess;
  aacOut: Readable;
}

export function createEncodeProcess(
  pcmStream: Readable, 
  sampleRate: number, 
  channels: number
): EncodeResult {
  const args = [
    '-f', 's16le',                    // Input format: raw PCM
    '-ar', sampleRate.toString(),     // Must match decode output
    '-ac', channels.toString(),       // Must match decode output
    '-i', 'pipe:0',                   // PCM input from Node.js transform
    '-c:a', 'aac',                    // Encode to AAC
    '-b:a', '128k',                   // Audio bitrate
    '-f', 'nut',                      // Nut container with timestamps
    '-fflags', '+genpts',             // Generate timestamps if needed
    'pipe:1'                          // Encoded audio to stdout
  ];

  const ffmpegProcess = spawn('ffmpeg', args, {
    stdio: ['pipe', 'pipe', 'pipe']
  });

  // Pipe PCM audio to FFmpeg stdin
  pcmStream.pipe(ffmpegProcess.stdin!);

  // Get AAC output stream
  const aacOut = ffmpegProcess.stdout as Readable;

  // Monitor stderr for errors
  ffmpegProcess.stderr!.on('data', (data: Buffer) => {
    console.log(`[ENCODE]: ${data.toString()}`);
  });

  ffmpegProcess.on('exit', (code, signal) => {
    console.log(`[ENCODE] Process exited with code ${code} and signal ${signal}`);
  });

  ffmpegProcess.on('error', (err) => {
    console.error('[ENCODE] Process error:', err);
  });

  return {
    process: ffmpegProcess,
    aacOut
  };
}

