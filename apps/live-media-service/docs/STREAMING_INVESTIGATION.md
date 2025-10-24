# FFmpeg Streaming Investigation Summary

## Question
What's the best practice for FFmpeg publishing streams: stdin or file list?

## TL;DR
**For this project: Use stdin piping** ✅

Your use case (continuous live streaming with pre-processed fragmented MP4s) is perfectly suited for stdin piping rather than concat demuxer.

---

## Quick Comparison

| Feature | stdin Piping | Concat Demuxer |
|---------|-------------|----------------|
| **Latency** | Lower ⚡ | Higher 🐌 |
| **Complexity** | Simpler ✅ | More complex ⚠️ |
| **Format Support** | fMP4, TS | All formats ✅ |
| **State Management** | Single process | File + reload signals |
| **Your Format (fMP4)** | ✅ Perfect match | ❌ Overkill |
| **Continuous Streaming** | ✅ Natural fit | ⚠️ Requires tricks |
| **Empty Start Issue** | ✅ No issue | ❌ Current bug |

---

## The Current Problem Explained

### What's Happening Now (Concat Demuxer)

```
1. Pipeline starts
2. StreamPublisher.start() creates EMPTY concat file
3. FFmpeg starts reading empty concat file
4. FFmpeg immediately exits (nothing to read)
5. isPublishing = false
6. Later: Fragment ready → publishFragment() called
7. ❌ Error: "Not currently publishing"
```

### Current FFmpeg Command
```bash
ffmpeg -re -f concat -safe 0 -i /tmp/concat-test-stream.txt \
  -c:v copy -c:a copy -f flv rtmp://localhost/live/test-stream
```

**Problem:** The concat file (`/tmp/concat-test-stream.txt`) is empty when FFmpeg starts!

---

## Recommended Solution: Switch to stdin

### Why stdin is Better for Your Case

1. **You're already using fragmented MP4** (`-movflags frag_keyframe+empty_moov`)
   - Perfect for streaming without seeking
   - Can be concatenated directly in a stream

2. **Continuous nature matches your pipeline**
   - Fragments arrive asynchronously
   - stdin naturally handles this flow

3. **Simpler state management**
   - One FFmpeg process for entire session
   - No concat file management
   - No SIGHUP signaling

4. **Lower latency**
   - Direct fragment → stdin → RTMP
   - No file polling/reloading

5. **Fixes empty start bug**
   - FFmpeg waits on stdin for data
   - Doesn't exit if no data initially

### Implementation Example

```typescript
export class StreamPublisher extends EventEmitter {
  private ffmpegProcess: ChildProcess | null = null;
  private stdinStream: Writable | null = null;
  private isPublishing: boolean = false;

  async start(): Promise<void> {
    const rtmpUrl = `${this.config.srsRtmpUrl}/${this.config.streamId}`;

    // FFmpeg reads fMP4 from stdin
    this.ffmpegProcess = spawn('ffmpeg', [
      '-re',              // Read at native frame rate
      '-f', 'mp4',        // Input format is MP4
      '-i', 'pipe:0',     // Read from stdin
      '-c:v', 'copy',     // Copy video codec
      '-c:a', 'copy',     // Copy audio codec
      '-f', 'flv',        // Output format for RTMP
      '-flvflags', 'no_duration_filesize',
      rtmpUrl
    ]);

    this.stdinStream = this.ffmpegProcess.stdin!;
    
    // Handle FFmpeg lifecycle
    this.ffmpegProcess.on('close', (code) => {
      this.log('warn', `FFmpeg exited with code ${code}`);
      this.isPublishing = false;
    });

    this.isPublishing = true;
    this.log('info', 'FFmpeg started, ready to receive fragments via stdin');
  }

  async publishFragment(output: RemuxedOutput): Promise<void> {
    if (!this.isPublishing || !this.stdinStream) {
      throw new Error('Not currently publishing');
    }

    try {
      // Read fragment file
      const fragmentData = await fs.readFile(output.outputPath);
      
      // Write to stdin
      const canContinue = this.stdinStream.write(fragmentData);
      
      // Handle backpressure (if write buffer is full)
      if (!canContinue) {
        await once(this.stdinStream, 'drain');
      }

      this.log('info', `Streamed fragment ${output.batchNumber} (${fragmentData.length} bytes)`);
      this.emit('fragment:published', output.batchNumber);
      
    } catch (error) {
      this.log('error', 'Failed to publish fragment:', error);
      this.emit('error', error as Error);
      throw error;
    }
  }

  async stop(): Promise<void> {
    if (!this.isPublishing) return;

    // Close stdin gracefully
    if (this.stdinStream) {
      this.stdinStream.end();
    }

    // Wait for FFmpeg to finish processing
    if (this.ffmpegProcess) {
      await new Promise<void>((resolve) => {
        this.ffmpegProcess!.once('close', () => resolve());
        
        // Timeout after 5 seconds
        setTimeout(() => {
          this.ffmpegProcess?.kill('SIGKILL');
          resolve();
        }, 5000);
      });
    }

    this.isPublishing = false;
    this.emit('stopped');
  }
}
```

### Key Implementation Notes

1. **Fragment Format**: Your remuxer already outputs fMP4 ✅
   ```typescript
   '-movflags', 'frag_keyframe+empty_moov'  // In Remuxer.ts line 122
   ```

2. **Backpressure Handling**: Important for smooth streaming
   ```typescript
   if (!stdin.write(data)) {
     await once(stdin, 'drain');  // Wait for buffer to drain
   }
   ```

3. **Error Recovery**: If FFmpeg crashes, restart it
   ```typescript
   ffmpegProcess.on('close', (code) => {
     if (code !== 0) {
       this.log('error', 'FFmpeg crashed, may need restart');
       // Could implement auto-restart here
     }
   });
   ```

4. **Clean Shutdown**: Close stdin to signal end of stream
   ```typescript
   stdinStream.end();  // Tells FFmpeg no more data coming
   ```

---

## Alternative: Fix Concat Approach (Not Recommended)

If you really want to keep concat demuxer, you can fix the empty start issue:

```typescript
async start(): Promise<void> {
  // DON'T start FFmpeg yet
  this.concatListPath = `/tmp/concat-${this.config.streamId}.txt`;
  await fs.writeFile(this.concatListPath, '');
  this.isPublishing = true;  // Mark as "ready to publish"
  this.log('info', 'Publisher initialized, waiting for first fragment');
}

async publishFragment(output: RemuxedOutput): Promise<void> {
  if (!this.isPublishing) {
    throw new Error('Not currently publishing');
  }

  // Append to concat list
  await fs.appendFile(
    this.concatListPath,
    `file '${output.outputPath}'\n`
  );

  // Start FFmpeg on FIRST fragment
  if (!this.ffmpegProcess) {
    this.log('info', 'First fragment received, starting FFmpeg');
    this.startFFmpegProcess();
  } else {
    // Reload for subsequent fragments
    process.kill(this.ffmpegProcess.pid, 'SIGHUP');
  }
  
  this.emit('fragment:published', output.batchNumber);
}
```

**But this still has issues:**
- Concat list management complexity
- SIGHUP signaling overhead  
- Disk I/O for every fragment
- Less natural for continuous streaming

---

## Testing Both Approaches

Run the test script to see both methods in action:

```bash
cd apps/live-media-service
./scripts/test-streaming-approaches.sh
```

This will:
1. Test concat demuxer approach
2. Test stdin piping approach  
3. Test continuous stdin (realistic simulation)

---

## Performance Characteristics

### stdin Piping
```
Fragment Ready (batch-0.mp4, 8.8MB)
        ↓
  Read file (~10ms)
        ↓
  Write to stdin (~5ms)
        ↓
  FFmpeg processes (~realtime)
        ↓
  RTMP publish
        
Total overhead: ~15ms + encoding time
```

### Concat Demuxer
```
Fragment Ready (batch-0.mp4, 8.8MB)
        ↓
  Append to concat list (~1ms)
        ↓
  Send SIGHUP signal (~1ms)
        ↓
  FFmpeg reloads list (~10-50ms)
        ↓
  FFmpeg opens file (~5ms)
        ↓
  FFmpeg reads file (~10ms)
        ↓
  RTMP publish
        
Total overhead: ~27-67ms + encoding time
```

---

## Recommendation

**Switch to stdin piping** for:
- ✅ Simpler architecture
- ✅ Lower latency
- ✅ Better match for continuous streaming
- ✅ Fixes "Not currently publishing" bug
- ✅ Cleaner state management
- ✅ Your fragments are already in the right format (fMP4)

---

## Related Documentation

- [Full Comparison](./FFMPEG_STREAMING_COMPARISON.md) - Detailed analysis
- [Test Script](../scripts/test-streaming-approaches.sh) - Practical testing
- [FFmpeg Protocols](https://ffmpeg.org/ffmpeg-protocols.html#pipe) - Official docs

---

## Next Steps

1. **Test current setup** to verify the bug:
   ```bash
   npm run dev
   # Watch for "Not currently publishing" error
   ```

2. **Run comparison tests**:
   ```bash
   ./scripts/test-streaming-approaches.sh
   ```

3. **Implement stdin approach** in `StreamPublisher.ts`

4. **Update tests** to verify new implementation

5. **Update documentation** with new architecture

