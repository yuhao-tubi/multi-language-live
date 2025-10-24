# FFmpeg Streaming Approaches: stdin vs File List

## Overview
Comparing two approaches for streaming pre-processed fragments to RTMP:

1. **stdin Piping**: Feed fragments directly to FFmpeg via stdin ✅ **IMPLEMENTED**
2. **Concat Demuxer**: Use file list with concat protocol (deprecated)

---

## Approach 1: stdin Piping

### How It Works
```bash
# Create a named pipe or stream directly
cat batch-0.mp4 batch-1.mp4 batch-2.mp4 | ffmpeg -i pipe:0 -c copy -f flv rtmp://...
```

### Pros
✅ **Real-time streaming**: Process fragments immediately as they become available
✅ **No intermediate files**: Concat list not needed
✅ **Simple state management**: Just keep the pipe open
✅ **Better for continuous streams**: Natural flow of data
✅ **Lower latency**: No file polling/reloading needed

### Cons
❌ **Format limitations**: Some container formats require seekable input
❌ **Buffer management**: Need to handle backpressure properly
❌ **Single FFmpeg instance**: Must keep process alive entire session
❌ **Restart complexity**: If FFmpeg crashes, must reconnect pipe
❌ **MP4 fragmented format required**: Regular MP4 won't work (needs fMP4)

### Code Pattern
```typescript
private ffmpegProcess: ChildProcess;
private stdinStream: Writable;

async start() {
  this.ffmpegProcess = spawn('ffmpeg', [
    '-f', 'mp4',           // Input format
    '-i', 'pipe:0',        // Read from stdin
    '-c:v', 'copy',
    '-c:a', 'copy',
    '-f', 'flv',
    rtmpUrl
  ]);
  
  this.stdinStream = this.ffmpegProcess.stdin;
}

async publishFragment(output: RemuxedOutput) {
  const data = await fs.readFile(output.outputPath);
  
  // Write to stdin
  if (!this.stdinStream.write(data)) {
    // Handle backpressure
    await new Promise(resolve => this.stdinStream.once('drain', resolve));
  }
}
```

---

## Approach 2: Concat Demuxer with File List

### How It Works
```bash
# Create concat list
echo "file '/path/to/batch-0.mp4'" > list.txt
echo "file '/path/to/batch-1.mp4'" >> list.txt

# Stream from list
ffmpeg -f concat -safe 0 -i list.txt -c copy -f flv rtmp://...
```

### Pros
✅ **Format flexibility**: Works with any container format
✅ **Restart resilient**: Can restart FFmpeg anytime
✅ **Simpler debugging**: Files persist on disk
✅ **State recovery**: Can inspect/replay files if needed
✅ **Multiple container support**: MP4, MKV, etc. all work

### Cons
❌ **Disk I/O overhead**: Reading/writing concat list repeatedly
❌ **Polling/reloading**: Need mechanism to notify FFmpeg of new files
❌ **Empty list issue**: FFmpeg fails if list is empty initially
❌ **Cleanup required**: Must manage concat list file lifecycle
❌ **Synchronization complexity**: Race conditions between writing list and FFmpeg reading

### Code Pattern (Current Implementation)
```typescript
async publishFragment(output: RemuxedOutput) {
  // Append to concat list
  await fs.appendFile(
    this.concatListPath,
    `file '${output.outputPath}'\n`
  );
  
  // Signal FFmpeg to reload (SIGHUP)
  if (this.ffmpegProcess?.pid) {
    process.kill(this.ffmpegProcess.pid, 'SIGHUP');
  }
}
```

---

## Approach 3: Hybrid - Segment Protocol (HLS/DASH Style)

### How It Works
```bash
# FFmpeg in segment mode
ffmpeg -i input -f segment -segment_time 10 -segment_list playlist.m3u8 output%03d.ts
```

### Characteristics
- Built for adaptive streaming scenarios
- Not ideal for our use case (we already have pre-processed fragments)
- Better suited when FFmpeg does the segmentation

---

## Recommendation for This Project

### Current Situation
- Pre-processed MP4 fragments arrive asynchronously
- Need continuous RTMP publishing
- Want low-latency end-to-end pipeline
- Using fragmented MP4 (fMP4) format

### Best Approach: **stdin Piping** (Approach 1)

**Why:**

1. **Continuous Stream Nature**: Your pipeline processes fragments continuously - stdin matches this model perfectly

2. **Already Using fMP4**: Your remuxer outputs with `-movflags frag_keyframe+empty_moov`, which is perfect for streaming

3. **Lower Complexity**: No concat list management, file signaling, or reload mechanisms

4. **Better Latency**: Direct pipe means fragment → RTMP with minimal delay

5. **Cleaner State**: Single long-running FFmpeg process mirrors the continuous nature of live streaming

### Implementation Strategy

```typescript
// Start FFmpeg once with stdin open
async start() {
  const ffmpeg = spawn('ffmpeg', [
    '-re',                    // Read at native frame rate
    '-f', 'mp4',              // Input is MP4
    '-i', 'pipe:0',           // From stdin
    '-c:v', 'copy',           // Copy video
    '-c:a', 'copy',           // Copy audio  
    '-f', 'flv',              // RTMP needs FLV
    '-flvflags', 'no_duration_filesize',  // Don't need total duration
    rtmpUrl
  ]);
  
  this.stdin = ffmpeg.stdin;
}

// Stream each fragment as it arrives
async publishFragment(output: RemuxedOutput) {
  const fragmentData = await fs.readFile(output.outputPath);
  
  // Handle backpressure
  if (!this.stdin.write(fragmentData)) {
    await once(this.stdin, 'drain');
  }
}
```

### Key Considerations

1. **Fragment Format**: Ensure remuxer outputs fragmented MP4 (already doing this ✓)

2. **Initialization Segment**: First fragment may need special handling if it contains moov atom

3. **Error Recovery**: If FFmpeg crashes, restart and potentially replay last fragment

4. **Backpressure**: Monitor stdin buffer and handle `drain` events

5. **Clean Shutdown**: Properly close stdin and wait for FFmpeg to finish

---

## Alternative: Concat with Lazy Start

If you want to keep the concat approach but fix current issues:

```typescript
async start() {
  // Don't start FFmpeg yet!
  this.isPublishing = false;
}

async publishFragment(output: RemuxedOutput) {
  // Append to list
  await fs.appendFile(listPath, `file '${output.outputPath}'\n`);
  
  // Start FFmpeg on first fragment
  if (!this.isPublishing) {
    this.startFFmpegProcess();
    this.isPublishing = true;
  } else {
    // Signal reload for subsequent fragments
    process.kill(this.ffmpegProcess.pid, 'SIGHUP');
  }
}
```

This fixes the empty list problem but still has the concat overhead.

---

## Conclusion

**Recommended:** Switch to **stdin piping** for:
- Simpler architecture
- Lower latency
- Better match for continuous streaming
- Cleaner state management

**Keep concat only if:** You need restart resilience or want files on disk for debugging.

