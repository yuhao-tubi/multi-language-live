import { spawn, ChildProcess } from 'child_process';
import { Readable } from 'stream';

/**
 * Process 4: Remux and RTMP Push
 * Combines untouched video with processed audio, pushes to SRS
 * 
 * Inputs:
 *   - Video stream (fd 3) in Nut format
 *   - Audio stream (fd 4) in Nut format
 * Output: RTMP push to SRS
 */

export interface RemuxResult {
  process: ChildProcess;
}

export function createRemuxProcess(
  videoStream: Readable, 
  audioStream: Readable, 
  rtmpUrl: string
): RemuxResult {
  const args = [
    '-f', 'nut',                              // Video input format
    '-i', 'pipe:3',                           // Original video from demux (fd 3)
    '-f', 'nut',                              // Audio input format
    '-i', 'pipe:4',                           // Processed audio from encoder (fd 4)
    '-map', '0:v',                            // Take video from first input
    '-c:v', 'copy',                           // Copy video (no re-encoding)
    '-map', '1:a',                            // Take audio from second input
    '-c:a', 'copy',                           // Copy audio (already AAC encoded)
    rtmpUrl                                   // Push to SRS
  ];

  // Configure stdio with video and audio input pipes
  // fd 0: stdin (unused)
  // fd 1: stdout (unused)
  // fd 2: stderr (logs)
  // fd 3: video input
  // fd 4: audio input
  const ffmpegProcess = spawn('ffmpeg', args, {
    stdio: ['ignore', 'pipe', 'pipe', 'pipe', 'pipe']
  });

  // Pipe video and audio streams to FFmpeg
  videoStream.pipe(ffmpegProcess.stdio[3] as NodeJS.WritableStream);
  audioStream.pipe(ffmpegProcess.stdio[4] as NodeJS.WritableStream);

  // Monitor stderr for RTMP connection status and errors
  ffmpegProcess.stderr!.on('data', (data: Buffer) => {
    console.log(`[REMUX]: ${data.toString()}`);
  });

  ffmpegProcess.on('exit', (code, signal) => {
    console.log(`[REMUX] Process exited with code ${code} and signal ${signal}`);
  });

  ffmpegProcess.on('error', (err) => {
    console.error('[REMUX] Process error:', err);
  });

  return {
    process: ffmpegProcess
  };
}

