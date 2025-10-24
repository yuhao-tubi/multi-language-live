/**
 * Unit tests for StorageService
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { StorageService } from '../../src/services/storage.service.js';
import path from 'path';
import fs from 'fs-extra';
import { initLogger } from '../../src/utils/logger.js';

// Initialize logger for tests
initLogger({
  level: 'error', // Only show errors in tests
  format: 'simple',
  toFile: false,
  toConsole: false,
  logsPath: './test-logs',
});

describe('StorageService', () => {
  let storageService: StorageService;
  const testBasePath = path.resolve(__dirname, '../fixtures/test-storage');

  beforeEach(async () => {
    // Clean up test directory before each test
    await fs.remove(testBasePath);

    storageService = new StorageService({
      basePath: testBasePath,
      originalStreamPath: path.join(testBasePath, 'original_stream'),
      processedFragmentsPath: path.join(testBasePath, 'processed_fragments'),
      logsPath: path.join(testBasePath, 'logs'),
    });
  });

  afterEach(async () => {
    // Clean up after each test
    await fs.remove(testBasePath);
  });

  describe('initialize', () => {
    it('should create all required directories', async () => {
      await storageService.initialize();

      expect(await fs.pathExists(testBasePath)).toBe(true);
      expect(await fs.pathExists(path.join(testBasePath, 'original_stream'))).toBe(true);
      expect(await fs.pathExists(path.join(testBasePath, 'processed_fragments'))).toBe(true);
      expect(await fs.pathExists(path.join(testBasePath, 'processed_fragments/video'))).toBe(true);
      expect(await fs.pathExists(path.join(testBasePath, 'processed_fragments/audio'))).toBe(true);
      expect(await fs.pathExists(path.join(testBasePath, 'processed_fragments/processed_audio'))).toBe(true);
      expect(await fs.pathExists(path.join(testBasePath, 'processed_fragments/output'))).toBe(true);
      expect(await fs.pathExists(path.join(testBasePath, 'logs'))).toBe(true);
    });

    it('should not fail if directories already exist', async () => {
      await storageService.initialize();
      await expect(storageService.initialize()).resolves.not.toThrow();
    });
  });

  describe('path getters', () => {
    it('should return correct segment path', () => {
      const path = storageService.getSegmentPath('stream-1', 'seg-001');
      expect(path).toContain('original_stream');
      expect(path).toContain('stream-1');
      expect(path).toContain('seg-001.ts');
    });

    it('should return correct batch path', () => {
      const path = storageService.getBatchPath('stream-1', 5);
      expect(path).toContain('original_stream');
      expect(path).toContain('stream-1');
      expect(path).toContain('batch-5.ts');
    });

    it('should return correct video path', () => {
      const path = storageService.getVideoPath('stream-1', 5);
      expect(path).toContain('processed_fragments/video');
      expect(path).toContain('stream-1');
      expect(path).toContain('batch-5.fmp4');
    });

    it('should return correct audio path', () => {
      const path = storageService.getAudioPath('stream-1', 5);
      expect(path).toContain('processed_fragments/audio');
      expect(path).toContain('stream-1');
      expect(path).toContain('batch-5.fmp4');
    });

    it('should return correct processed audio path', () => {
      const path = storageService.getProcessedAudioPath('stream-1', 5);
      expect(path).toContain('processed_fragments/processed_audio');
      expect(path).toContain('stream-1');
      expect(path).toContain('batch-5.fmp4');
    });

    it('should return correct output path', () => {
      const path = storageService.getOutputPath('stream-1', 5);
      expect(path).toContain('processed_fragments/output');
      expect(path).toContain('stream-1');
      expect(path).toContain('batch-5.fmp4');
    });
  });

  describe('file operations', () => {
    beforeEach(async () => {
      await storageService.initialize();
    });

    it('should save and read file', async () => {
      const testData = Buffer.from('test data');
      const filePath = path.join(testBasePath, 'test-file.txt');

      await storageService.saveFile(filePath, testData);
      const readData = await storageService.readFile(filePath);

      expect(readData.toString()).toBe('test data');
    });

    it('should check if file exists', async () => {
      const testData = Buffer.from('test data');
      const filePath = path.join(testBasePath, 'test-file.txt');

      expect(await storageService.fileExists(filePath)).toBe(false);

      await storageService.saveFile(filePath, testData);

      expect(await storageService.fileExists(filePath)).toBe(true);
    });

    it('should get file size', async () => {
      const testData = Buffer.from('test data');
      const filePath = path.join(testBasePath, 'test-file.txt');

      await storageService.saveFile(filePath, testData);
      const size = await storageService.getFileSize(filePath);

      expect(size).toBe(testData.length);
    });

    it('should delete file', async () => {
      const testData = Buffer.from('test data');
      const filePath = path.join(testBasePath, 'test-file.txt');

      await storageService.saveFile(filePath, testData);
      expect(await storageService.fileExists(filePath)).toBe(true);

      await storageService.deleteFile(filePath);
      expect(await storageService.fileExists(filePath)).toBe(false);
    });

    it('should create parent directories when saving file', async () => {
      const testData = Buffer.from('test data');
      const filePath = path.join(testBasePath, 'nested/deep/path/test-file.txt');

      await storageService.saveFile(filePath, testData);

      expect(await storageService.fileExists(filePath)).toBe(true);
    });
  });

  describe('getStats', () => {
    beforeEach(async () => {
      await storageService.initialize();
    });

    it('should return statistics for empty storage', async () => {
      const stats = await storageService.getStats();

      expect(stats.totalSize).toBe(0);
      expect(stats.fileCount).toBe(0);
      expect(stats.breakdown.originalSegments).toBe(0);
      expect(stats.breakdown.videoFragments).toBe(0);
      expect(stats.breakdown.audioFragments).toBe(0);
      expect(stats.breakdown.processedAudio).toBe(0);
      expect(stats.breakdown.remuxedOutput).toBe(0);
    });

    it('should calculate statistics correctly', async () => {
      // Create test files
      const testData = Buffer.from('test data');
      
      await storageService.saveFile(
        storageService.getSegmentPath('stream-1', 'seg-1'),
        testData
      );
      await storageService.saveFile(
        storageService.getVideoPath('stream-1', 1),
        testData
      );

      const stats = await storageService.getStats();

      expect(stats.totalSize).toBeGreaterThan(0);
      expect(stats.fileCount).toBeGreaterThan(0);
      expect(stats.breakdown.originalSegments).toBeGreaterThan(0);
      expect(stats.breakdown.videoFragments).toBeGreaterThan(0);
    });
  });

  describe('cleanOldFiles', () => {
    beforeEach(async () => {
      await storageService.initialize();
    });

    it('should not delete recent files', async () => {
      const testData = Buffer.from('test data');
      const filePath = storageService.getSegmentPath('stream-1', 'seg-1');

      await storageService.saveFile(filePath, testData);

      const deletedCount = await storageService.cleanOldFiles(1);

      expect(deletedCount).toBe(0);
      expect(await storageService.fileExists(filePath)).toBe(true);
    });

    it('should delete old files', async () => {
      const testData = Buffer.from('test data');
      const filePath = storageService.getSegmentPath('stream-1', 'seg-1');

      await storageService.saveFile(filePath, testData);

      // Modify file timestamp to be old
      const oldTime = Date.now() - (25 * 60 * 60 * 1000); // 25 hours ago
      await fs.utimes(filePath, oldTime / 1000, oldTime / 1000);

      const deletedCount = await storageService.cleanOldFiles(24);

      expect(deletedCount).toBeGreaterThan(0);
      expect(await storageService.fileExists(filePath)).toBe(false);
    });
  });

  describe('cleanAll', () => {
    beforeEach(async () => {
      await storageService.initialize();
    });

    it('should remove all files and recreate structure', async () => {
      // Create some test files
      const testData = Buffer.from('test data');
      await storageService.saveFile(storageService.getSegmentPath('stream-1', 'seg-1'), testData);
      await storageService.saveFile(storageService.getVideoPath('stream-1', 1), testData);

      await storageService.cleanAll();

      const stats = await storageService.getStats();
      expect(stats.totalSize).toBe(0);
      expect(stats.fileCount).toBe(0);

      // Verify directories still exist
      expect(await fs.pathExists(path.join(testBasePath, 'original_stream'))).toBe(true);
      expect(await fs.pathExists(path.join(testBasePath, 'processed_fragments'))).toBe(true);
    });
  });
});

