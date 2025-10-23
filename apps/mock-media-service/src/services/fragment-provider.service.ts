import { EventEmitter } from 'events';
import * as fs from 'fs-extra';
import * as path from 'path';
import { AudioFragment, FragmentDelivery } from '../types';

export class FragmentProvider extends EventEmitter {
  private activeStreams: Map<string, NodeJS.Timeout> = new Map();
  private streamCounters: Map<string, number> = new Map();
  private readonly fragmentsBasePath: string;
  private readonly fragmentInterval: number;
  private readonly maxFragments: number;

  constructor(
    fragmentsBasePath: string,
    fragmentInterval: number = 15000,
    maxFragments: number = 4
  ) {
    super();
    this.fragmentsBasePath = fragmentsBasePath;
    this.fragmentInterval = fragmentInterval;
    this.maxFragments = maxFragments;
  }

  async getAvailableStreams(): Promise<string[]> {
    try {
      const exists = await fs.pathExists(this.fragmentsBasePath);
      if (!exists) {
        console.log(`Fragments directory does not exist: ${this.fragmentsBasePath}`);
        return [];
      }

      const entries = await fs.readdir(this.fragmentsBasePath, { withFileTypes: true });
      return entries
        .filter(entry => entry.isDirectory())
        .map(entry => entry.name);
    } catch (error) {
      console.error('Error reading available streams:', error);
      return [];
    }
  }

  async startStream(streamId: string): Promise<void> {
    if (this.activeStreams.has(streamId)) {
      console.log(`Stream ${streamId} is already active`);
      return;
    }

    console.log(`Starting stream: ${streamId}`);
    this.streamCounters.set(streamId, 0);

    // Immediately send first fragment
    await this.sendNextFragment(streamId);

    // Schedule subsequent fragments
    const intervalId = setInterval(async () => {
      await this.sendNextFragment(streamId);
    }, this.fragmentInterval);

    this.activeStreams.set(streamId, intervalId);
  }

  stopStream(streamId: string): void {
    const intervalId = this.activeStreams.get(streamId);
    if (intervalId) {
      clearInterval(intervalId);
      this.activeStreams.delete(streamId);
      this.streamCounters.delete(streamId);
      console.log(`Stopped stream: ${streamId}`);
    }
  }

  private async sendNextFragment(streamId: string): Promise<void> {
    try {
      const sequenceNumber = this.streamCounters.get(streamId) || 0;

      // Check if we've reached the max fragments limit
      if (sequenceNumber >= this.maxFragments) {
        console.log(`Stream ${streamId} reached max fragments (${this.maxFragments}), stopping...`);
        this.stopStream(streamId);
        this.emit('stream:complete', streamId);
        return;
      }

      const streamDir = path.join(this.fragmentsBasePath, streamId);
      const files = await fs.readdir(streamDir);
      const m4sFiles = files.filter(f => f.endsWith('.m4s')).sort();

      if (m4sFiles.length === 0) {
        console.error(`No m4s files found for stream ${streamId}`);
        this.emit('stream:error', streamId, new Error('No m4s files found'));
        this.stopStream(streamId);
        return;
      }

      // Cycle through available files if we have fewer than maxFragments
      const fileIndex = sequenceNumber % m4sFiles.length;
      const fileName = m4sFiles[fileIndex];
      const filePath = path.join(streamDir, fileName);

      const data = await fs.readFile(filePath);

      const fragment: AudioFragment = {
        id: `${streamId}-${sequenceNumber}`,
        streamId,
        sequenceNumber,
        timestamp: Date.now(),
        duration: 15000, // 15 seconds
        codec: 'aac',
        sampleRate: 44100,
        channels: 2,
        bitrate: 256000,
        metadata: {
          fileName,
          fileSize: data.length
        }
      };

      const delivery: FragmentDelivery = {
        fragment,
        data
      };

      this.streamCounters.set(streamId, sequenceNumber + 1);
      this.emit('fragment', streamId, delivery);

      console.log(`Sent fragment ${sequenceNumber + 1}/${this.maxFragments} for stream ${streamId} (${fileName}, ${data.length} bytes)`);
    } catch (error) {
      console.error(`Error sending fragment for stream ${streamId}:`, error);
      this.emit('stream:error', streamId, error);
    }
  }

  isStreamActive(streamId: string): boolean {
    return this.activeStreams.has(streamId);
  }

  getActiveStreamCount(): number {
    return this.activeStreams.size;
  }
}

