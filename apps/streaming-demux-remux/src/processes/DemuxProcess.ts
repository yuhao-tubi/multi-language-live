import { spawn, ChildProcess } from 'child_process';
import { Readable } from 'stream';

/**
 * Process 1: Demultiplexer
 * Separates video and audio streams from HLS input
 * 
 * Input: HLS stream (stdin)
 * Outputs: 
 *   - Video stream (fd 3) in Nut format
 *   - Audio stream (fd 4) in Nut format
 */

export interface DemuxResult {
  process: ChildProcess;
  videoOut: Readable;
  audioOut: Readable;
}

export function createDemuxProcess(inputStream: Readable): DemuxResult {
  const args = [
    '-i', 'pipe:0',           // HLS input from stdin
    '-map', '0:v',            // Select video stream
    '-c:v', 'copy',           // Copy video without re-encoding
    '-f', 'nut',              // Nut container preserves timestamps
    'pipe:3',                 // Video output to fd 3
    '-map', '0:a',            // Select audio stream
    '-c:a', 'copy',           // Keep audio compressed for now
    '-f', 'nut',              // Nut container for audio
    'pipe:4'                  // Audio output to fd 4
  ];

  // Configure stdio with extra file descriptors
  // fd 0: stdin (input)
  // fd 1: stdout (unused)
  // fd 2: stderr (logs)
  // fd 3: video output pipe
  // fd 4: audio output pipe
  const ffmpegProcess = spawn('ffmpeg', args, {
    stdio: ['pipe', 'pipe', 'pipe', 'pipe', 'pipe']
  });

  // Pipe input stream to FFmpeg stdin
  inputStream.pipe(ffmpegProcess.stdin!);

  // Get video and audio output streams
  const videoOut = ffmpegProcess.stdio[3] as Readable;
  const audioOut = ffmpegProcess.stdio[4] as Readable;

  // Monitor stderr for errors
  ffmpegProcess.stderr!.on('data', (data: Buffer) => {
    console.log(`[DEMUX]: ${data.toString()}`);
  });

  ffmpegProcess.on('exit', (code, signal) => {
    console.log(`[DEMUX] Process exited with code ${code} and signal ${signal}`);
  });

  ffmpegProcess.on('error', (err) => {
    console.error('[DEMUX] Process error:', err);
  });

  return {
    process: ffmpegProcess,
    videoOut,
    audioOut
  };
}

