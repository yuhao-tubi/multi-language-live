import * as fs from 'fs-extra';
import * as path from 'path';
import { spawn } from 'child_process';
import { AudioFragment } from '../types';

export class MediaOutputService {
  private readonly outputBasePath: string;
  private readonly outputAudioBasePath: string;
  private readonly outputVideoBasePath: string;
  private readonly videosBasePath: string;

  constructor(outputBasePath: string, videosBasePath: string) {
    this.outputBasePath = outputBasePath;
    this.outputAudioBasePath = path.join(this.outputBasePath, 'audio-fragments');
    this.outputVideoBasePath = path.join(this.outputBasePath, 'videos');
    this.videosBasePath = videosBasePath;
  }

  async saveProcessedFragment(fragment: AudioFragment, data: Buffer): Promise<string> {
    const streamDir = path.join(this.outputAudioBasePath, fragment.streamId);
    await fs.ensureDir(streamDir);

    const baseFileName = (fragment.metadata && fragment.metadata.fileName)
      ? String(fragment.metadata.fileName)
      : `fragment-${fragment.sequenceNumber}.m4s`;
    const filePath = path.join(streamDir, baseFileName);
    await fs.writeFile(filePath, data);
    return filePath;
  }

  async remuxStream(streamId: string): Promise<{ outputVideoPath: string }>{
    const sourceVideo = path.join(this.videosBasePath, `${streamId}.mp4`);
    const audioDir = path.join(this.outputAudioBasePath, streamId);
    const workDir = path.join(this.outputBasePath, '.work', streamId);
    const tmpAudio = path.join(workDir, 'tmp_audio.mp4');
    const listFile = path.join(workDir, 'list.txt');
    const outputVideo = path.join(this.outputVideoBasePath, `${streamId}.mp4`);

    // Preconditions
    if (!(await fs.pathExists(sourceVideo))) {
      throw new Error(`Source video not found: ${sourceVideo}`);
    }
    if (!(await fs.pathExists(audioDir))) {
      throw new Error(`Processed audio fragments directory not found: ${audioDir}`);
    }

    await fs.ensureDir(workDir);
    await fs.ensureDir(this.outputVideoBasePath);

    // Build concat list from m4s files
    const files = (await fs.readdir(audioDir))
      .filter(f => f.endsWith('.m4s'))
      .sort();

    if (files.length === 0) {
      throw new Error(`No processed audio fragments found in ${audioDir}`);
    }

    const listContent = files.map(f => `file '${path.join(audioDir, f).replace(/'/g, "'\\''")}'`).join('\n');
    await fs.writeFile(listFile, listContent);

    // Step 1: concat m4s audio segments into a single MP4 with copy
    await this.runFfmpeg([
      '-y',
      '-safe', '0',
      '-f', 'concat',
      '-i', listFile,
      '-c', 'copy',
      tmpAudio
    ]);

    // Step 2: replace audio in source video with concatenated audio
    await this.runFfmpeg([
      '-y',
      '-i', sourceVideo,
      '-i', tmpAudio,
      '-map', '0:v:0',
      '-map', '1:a:0',
      '-c:v', 'copy',
      '-c:a', 'copy',
      '-shortest',
      outputVideo
    ]);

    return { outputVideoPath: outputVideo };
  }

  async cleanOutput(streamId?: string): Promise<string[]> {
    const removed: string[] = [];
    if (streamId) {
      const dir = path.join(this.outputAudioBasePath, streamId);
      if (await fs.pathExists(dir)) {
        await fs.remove(dir);
        removed.push(dir);
      }
      return removed;
    }

    const exists = await fs.pathExists(this.outputAudioBasePath);
    if (!exists) return removed;

    const entries = await fs.readdir(this.outputAudioBasePath, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.isDirectory()) {
        const dir = path.join(this.outputAudioBasePath, entry.name);
        await fs.remove(dir);
        removed.push(dir);
      }
    }
    return removed;
  }

  private runFfmpeg(args: string[]): Promise<void> {
    return new Promise((resolve, reject) => {
      const proc = spawn('ffmpeg', args, { stdio: 'inherit' });
      proc.on('error', reject);
      proc.on('close', code => {
        if (code === 0) resolve();
        else reject(new Error(`ffmpeg exited with code ${code}`));
      });
    });
  }
}


