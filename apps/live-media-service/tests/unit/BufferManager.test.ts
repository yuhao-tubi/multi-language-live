/**
 * Unit tests for BufferManager
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { BufferManager } from '../../src/services/buffer-manager.service.js';
import { SegmentMetadata } from '../../src/types/index.js';
import { initLogger } from '../../src/utils/logger.js';

// Initialize logger for tests
initLogger({
  level: 'error',
  format: 'simple',
  toFile: false,
  toConsole: false,
  logsPath: './test-logs',
});

describe('BufferManager', () => {
  let bufferManager: BufferManager;
  const BUFFER_DURATION = 30; // 30 seconds

  beforeEach(() => {
    bufferManager = new BufferManager(BUFFER_DURATION);
  });

  const createSegment = (id: string, duration: number, size: number = 1024): SegmentMetadata => ({
    id,
    path: `/path/to/${id}.ts`,
    size,
    duration,
    timestamp: new Date(),
    sequence: parseInt(id.split('-')[1] || '0'),
  });

  describe('initialization', () => {
    it('should initialize with correct buffer duration', () => {
      const status = bufferManager.getStatus();
      expect(status.segmentCount).toBe(0);
      expect(status.currentDuration).toBe(0);
      expect(status.progress).toBe(0);
      expect(status.nextBatchNumber).toBe(0);
    });

    it('should allow custom buffer duration', () => {
      const customBuffer = new BufferManager(60);
      const status = customBuffer.getStatus();
      expect(status.progress).toBe(0);
    });
  });

  describe('addSegment', () => {
    it('should add segment and return null when buffer not full', () => {
      const segment = createSegment('seg-1', 10);
      const batch = bufferManager.addSegment(segment);

      expect(batch).toBeNull();

      const status = bufferManager.getStatus();
      expect(status.segmentCount).toBe(1);
      expect(status.currentDuration).toBe(10);
      expect(status.progress).toBeCloseTo(33.33, 1);
    });

    it('should return batch when buffer reaches threshold', () => {
      const segments = [
        createSegment('seg-1', 10),
        createSegment('seg-2', 10),
        createSegment('seg-3', 11), // Total: 31 seconds - exceeds 30
      ];

      let batch = null;
      for (let i = 0; i < segments.length - 1; i++) {
        batch = bufferManager.addSegment(segments[i]);
        expect(batch).toBeNull();
      }

      // Last segment should trigger batch creation (30 + 11 = 41 total, should batch at 30)
      batch = bufferManager.addSegment(segments[2]);
      expect(batch).not.toBeNull();
      expect(batch?.segments.length).toBe(3);
      expect(batch?.totalDuration).toBe(31);
      expect(batch?.batchNumber).toBe(0);
    });

    it('should reset buffer after creating batch', () => {
      const segments = [
        createSegment('seg-1', 15),
        createSegment('seg-2', 16), // Total: 31 seconds - exceeds 30
      ];

      let batch = null;
      for (const segment of segments) {
        batch = bufferManager.addSegment(segment);
      }

      // Last addSegment should have created a batch and reset buffer
      expect(batch).not.toBeNull();
      
      // Buffer should be empty after batch creation
      const status = bufferManager.getStatus();
      expect(status.segmentCount).toBe(0);
      expect(status.currentDuration).toBe(0);
      expect(status.nextBatchNumber).toBe(1);
    });

    it('should increment batch number for each batch', () => {
      const segments = [
        createSegment('seg-1', 30),
        createSegment('seg-2', 30),
      ];

      const batch1 = bufferManager.addSegment(segments[0]);
      expect(batch1?.batchNumber).toBe(0);

      const batch2 = bufferManager.addSegment(segments[1]);
      expect(batch2?.batchNumber).toBe(1);
    });

    it('should calculate total size correctly', () => {
      const segments = [
        createSegment('seg-1', 10, 1000),
        createSegment('seg-2', 10, 2000),
        // Don't add a third segment that would exceed threshold
      ];

      for (const segment of segments) {
        bufferManager.addSegment(segment);
      }

      const size = bufferManager.getCurrentSize();
      expect(size).toBe(3000);
    });
  });

  describe('flush', () => {
    it('should create batch with current segments even if not full', () => {
      const segments = [
        createSegment('seg-1', 10),
        createSegment('seg-2', 5),
      ];

      bufferManager.addSegment(segments[0]);
      bufferManager.addSegment(segments[1]);

      const batch = bufferManager.flush();
      expect(batch).not.toBeNull();
      expect(batch?.segments.length).toBe(2);
      expect(batch?.totalDuration).toBe(15);
      expect(batch?.batchNumber).toBe(0);
    });

    it('should return null if buffer is empty', () => {
      const batch = bufferManager.flush();
      expect(batch).toBeNull();
    });

    it('should reset buffer after flushing', () => {
      bufferManager.addSegment(createSegment('seg-1', 10));
      bufferManager.flush();

      const status = bufferManager.getStatus();
      expect(status.segmentCount).toBe(0);
      expect(status.currentDuration).toBe(0);
    });
  });

  describe('reset', () => {
    it('should clear buffer and reset counter', () => {
      bufferManager.addSegment(createSegment('seg-1', 30));
      bufferManager.addSegment(createSegment('seg-2', 10));

      bufferManager.reset();

      const status = bufferManager.getStatus();
      expect(status.segmentCount).toBe(0);
      expect(status.currentDuration).toBe(0);
      expect(status.nextBatchNumber).toBe(0);
    });
  });

  describe('getStatus', () => {
    it('should return correct status', () => {
      bufferManager.addSegment(createSegment('seg-1', 15));

      const status = bufferManager.getStatus();
      expect(status.segmentCount).toBe(1);
      expect(status.currentDuration).toBe(15);
      expect(status.progress).toBe(50);
      expect(status.nextBatchNumber).toBe(0);
    });
  });

  describe('getCurrentSize', () => {
    it('should return 0 for empty buffer', () => {
      expect(bufferManager.getCurrentSize()).toBe(0);
    });

    it('should return total size of segments', () => {
      bufferManager.addSegment(createSegment('seg-1', 10, 1000));
      bufferManager.addSegment(createSegment('seg-2', 10, 2000));

      expect(bufferManager.getCurrentSize()).toBe(3000);
    });
  });

  describe('isEmpty', () => {
    it('should return true for empty buffer', () => {
      expect(bufferManager.isEmpty()).toBe(true);
    });

    it('should return false for non-empty buffer', () => {
      bufferManager.addSegment(createSegment('seg-1', 10));
      expect(bufferManager.isEmpty()).toBe(false);
    });
  });

  describe('isReady', () => {
    it('should return false when buffer not full', () => {
      bufferManager.addSegment(createSegment('seg-1', 20));
      expect(bufferManager.isReady()).toBe(false);
    });

    it('should return false after automatically creating batch at threshold', () => {
      // When we add a segment that reaches threshold, batch is auto-created and buffer is reset
      bufferManager.addSegment(createSegment('seg-1', 30));
      // Buffer is now empty after auto-batch
      expect(bufferManager.isReady()).toBe(false);
    });

    it('should return false after automatically creating batch when exceeding threshold', () => {
      // When we add a segment that exceeds threshold, batch is auto-created and buffer is reset
      bufferManager.addSegment(createSegment('seg-1', 35));
      // Buffer is now empty after auto-batch
      expect(bufferManager.isReady()).toBe(false);
    });
  });

  describe('batch metadata', () => {
    it('should include timestamp in batch', () => {
      bufferManager.addSegment(createSegment('seg-1', 10));
      const batch = bufferManager.flush();

      expect(batch).not.toBeNull();
      expect(batch?.timestamp).toBeInstanceOf(Date);
    });

    it('should preserve segment order in batch', () => {
      const segments = [
        createSegment('seg-1', 8),
        createSegment('seg-2', 8),
        createSegment('seg-3', 8),
      ];

      for (const segment of segments) {
        bufferManager.addSegment(segment);
      }

      const batch = bufferManager.flush();
      expect(batch).not.toBeNull();
      expect(batch?.segments[0].id).toBe('seg-1');
      expect(batch?.segments[1].id).toBe('seg-2');
      expect(batch?.segments[2].id).toBe('seg-3');
    });
  });
});

