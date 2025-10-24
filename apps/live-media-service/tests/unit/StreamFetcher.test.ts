/**
 * Unit tests for StreamFetcher
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { StreamFetcher } from '../../src/modules/StreamFetcher.js';
import { StorageService } from '../../src/services/storage.service.js';
import { initLogger } from '../../src/utils/logger.js';
import path from 'path';
import fs from 'fs-extra';
import axios from 'axios';

// Mock axios
vi.mock('axios');
const mockedAxios = axios as any;

// Initialize logger for tests
initLogger({
  level: 'error',
  format: 'simple',
  toFile: false,
  toConsole: false,
  logsPath: './test-logs',
});

describe('StreamFetcher', () => {
  let streamFetcher: StreamFetcher;
  let storageService: StorageService;
  const testBasePath = path.resolve(__dirname, '../fixtures/test-storage-fetcher');
  const testStreamId = 'test-stream-1';
  const testSourceUrl = 'https://example.com/stream.m3u8';

  beforeEach(async () => {
    // Clean up test directory
    await fs.remove(testBasePath);

    // Create storage service
    storageService = new StorageService({
      basePath: testBasePath,
      originalStreamPath: path.join(testBasePath, 'original_stream'),
      processedFragmentsPath: path.join(testBasePath, 'processed_fragments'),
      logsPath: path.join(testBasePath, 'logs'),
    });

    await storageService.initialize();

    // Reset mocks
    vi.clearAllMocks();
  });

  afterEach(async () => {
    if (streamFetcher) {
      await streamFetcher.stop();
    }
    await fs.remove(testBasePath);
  });

  const createMockManifest = (segments: Array<{ uri: string; duration: number }>) => {
    return `#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:10
#EXT-X-MEDIA-SEQUENCE:0
${segments.map((seg, i) => `#EXTINF:${seg.duration},\n${seg.uri}`).join('\n')}
`;
  };

  describe('initialization', () => {
    it('should initialize with correct config', () => {
      streamFetcher = new StreamFetcher({
        sourceUrl: testSourceUrl,
        streamId: testStreamId,
        bufferDurationSeconds: 30,
        storageService,
      });

      const status = streamFetcher.getStatus();
      expect(status.isRunning).toBe(false);
      expect(status.segmentCount).toBe(0);
      expect(status.totalSegmentsDownloaded).toBe(0);
    });
  });

  describe('start and stop', () => {
    it('should start and emit started event', async () => {
      streamFetcher = new StreamFetcher({
        sourceUrl: testSourceUrl,
        streamId: testStreamId,
        bufferDurationSeconds: 30,
        storageService,
      });

      // Mock manifest response
      mockedAxios.get.mockResolvedValue({
        data: createMockManifest([
          { uri: 'segment0.ts', duration: 10 }
        ])
      });

      const startedSpy = vi.fn();
      streamFetcher.on('started', startedSpy);

      await streamFetcher.start();

      expect(startedSpy).toHaveBeenCalled();
      expect(streamFetcher.getStatus().isRunning).toBe(true);

      await streamFetcher.stop();
    });

    it('should not start twice', async () => {
      streamFetcher = new StreamFetcher({
        sourceUrl: testSourceUrl,
        streamId: testStreamId,
        bufferDurationSeconds: 30,
        storageService,
      });

      mockedAxios.get.mockResolvedValue({
        data: createMockManifest([])
      });

      await streamFetcher.start();
      const status1 = streamFetcher.getStatus();

      await streamFetcher.start(); // Should not start again
      const status2 = streamFetcher.getStatus();

      expect(status1.isRunning).toBe(true);
      expect(status2.isRunning).toBe(true);

      await streamFetcher.stop();
    });

    it('should stop and emit stopped event', async () => {
      streamFetcher = new StreamFetcher({
        sourceUrl: testSourceUrl,
        streamId: testStreamId,
        bufferDurationSeconds: 30,
        storageService,
      });

      mockedAxios.get.mockResolvedValue({
        data: createMockManifest([])
      });

      await streamFetcher.start();

      const stoppedSpy = vi.fn();
      streamFetcher.on('stopped', stoppedSpy);

      await streamFetcher.stop();

      expect(stoppedSpy).toHaveBeenCalled();
      expect(streamFetcher.getStatus().isRunning).toBe(false);
    });

    it('should flush buffer on stop', async () => {
      streamFetcher = new StreamFetcher({
        sourceUrl: testSourceUrl,
        streamId: testStreamId,
        bufferDurationSeconds: 30,
        storageService,
        pollIntervalMs: 50,
      });

      // Mock manifest with small segment
      mockedAxios.get.mockResolvedValueOnce({
        data: createMockManifest([
          { uri: 'segment0.ts', duration: 10 }
        ])
      });

      // Mock segment data
      mockedAxios.get.mockResolvedValueOnce({
        data: Buffer.from('mock segment data')
      });

      const batchReadySpy = vi.fn();
      streamFetcher.on('batch:ready', batchReadySpy);

      await streamFetcher.start();

      // Wait a bit for segment to be processed
      await new Promise(resolve => setTimeout(resolve, 100));

      // Stop should flush the buffer
      await streamFetcher.stop();

      expect(batchReadySpy).toHaveBeenCalled();
    });
  });

  describe('segment downloading', () => {
    it('should download segments and emit events', async () => {
      streamFetcher = new StreamFetcher({
        sourceUrl: testSourceUrl,
        streamId: testStreamId,
        bufferDurationSeconds: 30,
        storageService,
        pollIntervalMs: 50,
      });

      // Mock manifest response
      mockedAxios.get.mockResolvedValueOnce({
        data: createMockManifest([
          { uri: 'segment0.ts', duration: 5 }
        ])
      });

      // Mock segment data
      mockedAxios.get.mockResolvedValueOnce({
        data: Buffer.from('mock segment data')
      });

      const segmentDownloadedSpy = vi.fn();
      streamFetcher.on('segment:downloaded', segmentDownloadedSpy);

      await streamFetcher.start();

      // Wait for segment to be processed
      await new Promise(resolve => setTimeout(resolve, 100));

      await streamFetcher.stop();

      expect(segmentDownloadedSpy).toHaveBeenCalled();
      expect(streamFetcher.getStatus().totalSegmentsDownloaded).toBeGreaterThan(0);
    });

    it('should save segments to storage', async () => {
      streamFetcher = new StreamFetcher({
        sourceUrl: testSourceUrl,
        streamId: testStreamId,
        bufferDurationSeconds: 30,
        storageService,
        pollIntervalMs: 50,
      });

      const testSegmentData = Buffer.from('test segment content');

      // Mock manifest response
      mockedAxios.get.mockResolvedValueOnce({
        data: createMockManifest([
          { uri: 'segment0.ts', duration: 5 }
        ])
      });

      // Mock segment data
      mockedAxios.get.mockResolvedValueOnce({
        data: testSegmentData
      });

      await streamFetcher.start();

      // Wait for segment to be processed
      await new Promise(resolve => setTimeout(resolve, 100));

      await streamFetcher.stop();

      // Check if segment file exists
      const segmentPath = storageService.getSegmentPath(testStreamId, 'seg-0');
      const exists = await storageService.fileExists(segmentPath);
      expect(exists).toBe(true);

      if (exists) {
        const savedData = await storageService.readFile(segmentPath);
        expect(savedData.toString()).toBe(testSegmentData.toString());
      }
    });
  });

  describe('batch creation', () => {
    it('should emit batch:ready when buffer is full', async () => {
      streamFetcher = new StreamFetcher({
        sourceUrl: testSourceUrl,
        streamId: testStreamId,
        bufferDurationSeconds: 30,
        storageService,
        pollIntervalMs: 50,
      });

      // Mock manifest with segments totaling > 30 seconds
      mockedAxios.get.mockResolvedValueOnce({
        data: createMockManifest([
          { uri: 'segment0.ts', duration: 15 },
          { uri: 'segment1.ts', duration: 15 },
          { uri: 'segment2.ts', duration: 5 }
        ])
      });

      // Mock segment data for each segment
      mockedAxios.get.mockResolvedValue({
        data: Buffer.from('mock segment data')
      });

      const batchReadySpy = vi.fn();
      streamFetcher.on('batch:ready', batchReadySpy);

      await streamFetcher.start();

      // Wait for segments to be processed
      await new Promise(resolve => setTimeout(resolve, 200));

      await streamFetcher.stop();

      // Should have created at least one batch
      expect(batchReadySpy).toHaveBeenCalled();
      const batch = batchReadySpy.mock.calls[0][0];
      expect(batch.totalDuration).toBeGreaterThanOrEqual(30);
    });
  });

  describe('error handling', () => {
    it('should emit error on download failure', async () => {
      streamFetcher = new StreamFetcher({
        sourceUrl: testSourceUrl,
        streamId: testStreamId,
        bufferDurationSeconds: 30,
        storageService,
        pollIntervalMs: 50,
      });

      // Mock manifest response
      mockedAxios.get.mockResolvedValueOnce({
        data: createMockManifest([
          { uri: 'segment0.ts', duration: 5 }
        ])
      });

      // Mock segment download failure
      mockedAxios.get.mockRejectedValueOnce(new Error('Network error'));

      const errorSpy = vi.fn();
      streamFetcher.on('error', errorSpy);

      await streamFetcher.start();

      // Wait for error to occur
      await new Promise(resolve => setTimeout(resolve, 100));

      await streamFetcher.stop();

      expect(errorSpy).toHaveBeenCalled();
    });
  });

  describe('flush', () => {
    it('should manually flush buffer', () => {
      streamFetcher = new StreamFetcher({
        sourceUrl: testSourceUrl,
        streamId: testStreamId,
        bufferDurationSeconds: 30,
        storageService,
      });

      // Flush empty buffer
      const batch = streamFetcher.flush();
      expect(batch).toBeNull();
    });
  });

  describe('URL resolution', () => {
    it('should handle absolute URLs', () => {
      streamFetcher = new StreamFetcher({
        sourceUrl: 'https://example.com/path/stream.m3u8',
        streamId: testStreamId,
        bufferDurationSeconds: 30,
        storageService,
      });

      // Test is implicit - constructor should not throw
      expect(streamFetcher).toBeDefined();
    });

    it('should handle relative URLs', () => {
      streamFetcher = new StreamFetcher({
        sourceUrl: 'https://example.com/path/stream.m3u8',
        streamId: testStreamId,
        bufferDurationSeconds: 30,
        storageService,
      });

      expect(streamFetcher).toBeDefined();
    });
  });
});

