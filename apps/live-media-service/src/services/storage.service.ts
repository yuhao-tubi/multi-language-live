/**
 * Storage service for managing files and directories
 */
import fs from 'fs-extra';
import path from 'path';
import { StorageStats } from '../types/index.js';
import { getLogger } from '../utils/logger.js';

let logger: ReturnType<typeof getLogger> | null = null;

/**
 * Storage service for disk operations
 */
export class StorageService {
  private basePath: string;
  private originalStreamPath: string;
  private processedFragmentsPath: string;
  private logsPath: string;

  constructor(config: {
    basePath: string;
    originalStreamPath: string;
    processedFragmentsPath: string;
    logsPath: string;
  }) {
    this.basePath = config.basePath;
    this.originalStreamPath = config.originalStreamPath;
    this.processedFragmentsPath = config.processedFragmentsPath;
    this.logsPath = config.logsPath;

    // Lazy initialize logger
    if (!logger) {
      try {
        logger = getLogger().child({ context: 'StorageService' });
      } catch {
        // Logger not initialized yet, will use console fallback
        logger = null;
      }
    }
  }

  private log(level: 'debug' | 'info' | 'warn' | 'error', message: string, ...args: unknown[]): void {
    if (logger) {
      logger[level](message, ...args);
    }
  }

  /**
   * Initialize storage directories
   */
  async initialize(): Promise<void> {
    this.log('info', 'Initializing storage directories');

    const directories = [
      this.basePath,
      this.originalStreamPath,
      this.processedFragmentsPath,
      path.join(this.processedFragmentsPath, 'video'),
      path.join(this.processedFragmentsPath, 'audio'),
      path.join(this.processedFragmentsPath, 'processed_audio'),
      path.join(this.processedFragmentsPath, 'output'),
      this.logsPath,
    ];

    for (const dir of directories) {
      await fs.ensureDir(dir);
      this.log('debug', `Created directory: ${dir}`);
    }

    this.log('info', 'Storage directories initialized');
  }

  /**
   * Get path for original segment
   */
  getSegmentPath(streamId: string, segmentId: string): string {
    return path.join(this.originalStreamPath, streamId, `${segmentId}.ts`);
  }

  /**
   * Get path for concatenated batch
   */
  getBatchPath(streamId: string, batchNumber: number): string {
    return path.join(this.originalStreamPath, streamId, `batch-${batchNumber}.ts`);
  }

  /**
   * Get path for video fragment
   */
  getVideoPath(streamId: string, batchNumber: number): string {
    return path.join(this.processedFragmentsPath, 'video', streamId, `batch-${batchNumber}.mp4`);
  }

  /**
   * Get path for audio fragment
   */
  getAudioPath(streamId: string, batchNumber: number): string {
    return path.join(this.processedFragmentsPath, 'audio', streamId, `batch-${batchNumber}.mp4`);
  }

  /**
   * Get path for processed audio
   */
  getProcessedAudioPath(streamId: string, batchNumber: number): string {
    return path.join(this.processedFragmentsPath, 'processed_audio', streamId, `batch-${batchNumber}.mp4`);
  }

  /**
   * Get path for remuxed output
   */
  getOutputPath(streamId: string, batchNumber: number): string {
    return path.join(this.processedFragmentsPath, 'output', streamId, `batch-${batchNumber}.mp4`);
  }

  /**
   * Get output directory for a stream (where batch files are stored)
   */
  getOutputDirectory(streamId: string): string {
    return path.join(this.processedFragmentsPath, 'output', streamId);
  }

  /**
   * Ensure directory exists for a file path
   */
  async ensureDir(filePath: string): Promise<void> {
    const dir = path.dirname(filePath);
    await fs.ensureDir(dir);
  }

  /**
   * Save buffer to file
   */
  async saveFile(filePath: string, data: Buffer): Promise<void> {
    await this.ensureDir(filePath);
    await fs.writeFile(filePath, data);
    this.log('debug', `Saved file: ${filePath} (${data.length} bytes)`);
  }

  /**
   * Read file as buffer
   */
  async readFile(filePath: string): Promise<Buffer> {
    const data = await fs.readFile(filePath);
    this.log('debug', `Read file: ${filePath} (${data.length} bytes)`);
    return data;
  }

  /**
   * Check if file exists
   */
  async fileExists(filePath: string): Promise<boolean> {
    return fs.pathExists(filePath);
  }

  /**
   * Get file size in bytes
   */
  async getFileSize(filePath: string): Promise<number> {
    const stats = await fs.stat(filePath);
    return stats.size;
  }

  /**
   * Delete file
   */
  async deleteFile(filePath: string): Promise<void> {
    await fs.remove(filePath);
    this.log('debug', `Deleted file: ${filePath}`);
  }

  /**
   * Get storage statistics
   */
  async getStats(): Promise<StorageStats> {
    this.log('debug', 'Calculating storage statistics');

    const stats: StorageStats = {
      totalSize: 0,
      fileCount: 0,
      breakdown: {
        originalSegments: 0,
        videoFragments: 0,
        audioFragments: 0,
        processedAudio: 0,
        remuxedOutput: 0,
      },
      availableSpace: 0,
    };

    // Calculate sizes for each directory
    stats.breakdown.originalSegments = await this.getDirectorySize(this.originalStreamPath);
    stats.breakdown.videoFragments = await this.getDirectorySize(
      path.join(this.processedFragmentsPath, 'video')
    );
    stats.breakdown.audioFragments = await this.getDirectorySize(
      path.join(this.processedFragmentsPath, 'audio')
    );
    stats.breakdown.processedAudio = await this.getDirectorySize(
      path.join(this.processedFragmentsPath, 'processed_audio')
    );
    stats.breakdown.remuxedOutput = await this.getDirectorySize(
      path.join(this.processedFragmentsPath, 'output')
    );

    stats.totalSize = Object.values(stats.breakdown).reduce((sum, size) => sum + size, 0);

    // Count files
    stats.fileCount = await this.countFiles(this.basePath);

    // Get available space (this is an approximation)
    // Note: fs.statfs is not available in fs-extra, so we'll use a placeholder
    // In production, you might want to use a library like 'diskusage'
    stats.availableSpace = 0; // TODO: Implement disk space check

    this.log('debug', 'Storage statistics calculated', stats);
    return stats;
  }

  /**
   * Get total size of directory recursively
   */
  private async getDirectorySize(dirPath: string): Promise<number> {
    if (!(await fs.pathExists(dirPath))) {
      return 0;
    }

    let totalSize = 0;
    const items = await fs.readdir(dirPath, { withFileTypes: true });

    for (const item of items) {
      const itemPath = path.join(dirPath, item.name);
      if (item.isFile()) {
        const stats = await fs.stat(itemPath);
        totalSize += stats.size;
      } else if (item.isDirectory()) {
        totalSize += await this.getDirectorySize(itemPath);
      }
    }

    return totalSize;
  }

  /**
   * Count files recursively
   */
  private async countFiles(dirPath: string): Promise<number> {
    if (!(await fs.pathExists(dirPath))) {
      return 0;
    }

    let count = 0;
    const items = await fs.readdir(dirPath, { withFileTypes: true });

    for (const item of items) {
      const itemPath = path.join(dirPath, item.name);
      if (item.isFile()) {
        count++;
      } else if (item.isDirectory()) {
        count += await this.countFiles(itemPath);
      }
    }

    return count;
  }

  /**
   * Clean old files older than specified hours
   */
  async cleanOldFiles(maxAgeHours: number): Promise<number> {
    this.log('info', `Cleaning files older than ${maxAgeHours} hours`);

    const maxAgeMs = maxAgeHours * 60 * 60 * 1000;
    const now = Date.now();
    let deletedCount = 0;

    const directories = [
      this.originalStreamPath,
      path.join(this.processedFragmentsPath, 'video'),
      path.join(this.processedFragmentsPath, 'audio'),
      path.join(this.processedFragmentsPath, 'processed_audio'),
      path.join(this.processedFragmentsPath, 'output'),
    ];

    for (const dir of directories) {
      if (await fs.pathExists(dir)) {
        deletedCount += await this.cleanDirectory(dir, now, maxAgeMs);
      }
    }

    this.log('info', `Cleaned ${deletedCount} old files`);
    return deletedCount;
  }

  /**
   * Clean directory recursively
   */
  private async cleanDirectory(dirPath: string, now: number, maxAgeMs: number): Promise<number> {
    let count = 0;
    const items = await fs.readdir(dirPath, { withFileTypes: true });

    for (const item of items) {
      const itemPath = path.join(dirPath, item.name);
      
      if (item.isFile()) {
        const stats = await fs.stat(itemPath);
        const age = now - stats.mtimeMs;
        
        if (age > maxAgeMs) {
          await fs.remove(itemPath);
          count++;
        }
      } else if (item.isDirectory()) {
        count += await this.cleanDirectory(itemPath, now, maxAgeMs);
        
        // Remove empty directories
        const remaining = await fs.readdir(itemPath);
        if (remaining.length === 0) {
          await fs.rmdir(itemPath);
        }
      }
    }

    return count;
  }

  /**
   * Clean all storage (for testing/debugging)
   */
  async cleanAll(): Promise<void> {
    this.log('warn', 'Cleaning all storage');
    
    await fs.emptyDir(this.originalStreamPath);
    await fs.emptyDir(this.processedFragmentsPath);
    
    // Recreate subdirectories
    await this.initialize();
    
    this.log('info', 'All storage cleaned');
  }
}

