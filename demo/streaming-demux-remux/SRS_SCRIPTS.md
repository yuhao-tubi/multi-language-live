# SRS Management Scripts

Quick reference for managing the SRS (Simple Realtime Server) Docker container.

## Prerequisites

Make sure Docker Desktop is installed and running on your system:
- **macOS/Windows**: Start Docker Desktop application
- **Linux**: Ensure Docker daemon is running (`sudo systemctl start docker`)

## Available Commands

### Start SRS

```bash
npm run srs:start
```

**What it does:**
- Checks if SRS container already exists
- Creates and starts a new SRS container if it doesn't exist
- Starts existing container if it's stopped
- Configures ports: 1935 (RTMP), 1985 (API), 8080 (HTTP/HLS)

**Output:**
```
✅ SRS started successfully!

🌐 SRS Web UI: http://localhost:8080
📡 RTMP Port: 1935 (rtmp://localhost/live/stream)
🔧 API Port: 1985
```

### Stop SRS

```bash
npm run srs:stop
```

**What it does:**
- Stops the running SRS container
- Container is preserved and can be restarted later

### Restart SRS

```bash
npm run srs:restart
```

**What it does:**
- Stops and starts the SRS container
- Useful for applying configuration changes or recovering from errors

### View Logs

```bash
npm run srs:logs
```

**What it does:**
- Shows real-time SRS server logs
- Press `Ctrl+C` to exit log viewing (container keeps running)

**Useful for:**
- Debugging connection issues
- Monitoring incoming RTMP streams
- Checking HLS segment generation

### Remove Container

```bash
npm run srs:remove
```

**What it does:**
- Stops and completely removes the SRS container
- Frees up the container name for fresh start
- Use this if you want to start completely fresh

## Quick Start Workflow

```bash
# 1. Start SRS
npm run srs:start

# 2. Start your application
npm run dev

# 3. View SRS logs in another terminal (optional)
npm run srs:logs

# 4. When done, stop SRS
npm run srs:stop
```

## Troubleshooting

### "Cannot connect to the Docker daemon"

**Problem:** Docker is not running

**Solution:**
- **macOS/Windows:** Open Docker Desktop application
- **Linux:** Run `sudo systemctl start docker`

### "port is already allocated"

**Problem:** Another service is using the required ports

**Solution:**
```bash
# Find what's using the port
lsof -i :1935
lsof -i :8080

# Option 1: Stop the conflicting service
# Option 2: Remove and recreate SRS with different ports (requires editing scripts)
```

### SRS container exists but won't start

**Solution:**
```bash
# Remove and recreate container
npm run srs:remove
npm run srs:start
```

### Can't see HLS output

**Problem:** Pipeline hasn't generated segments yet, or SRS isn't running

**Solution:**
1. Wait 10-15 seconds after starting the pipeline
2. Check SRS is running: `npm run srs:logs`
3. Verify RTMP connection in logs: Look for "RTMP client connected"
4. Check HLS endpoint: `curl http://localhost:8080/live/processed.m3u8`

## Verifying SRS is Working

### Check Container Status
```bash
docker ps | grep srs
```

### Test API Endpoint
```bash
curl http://localhost:8080/api/v1/versions
```

Expected response:
```json
{
  "code": 0,
  "server": "SRS/5.x.x",
  ...
}
```

### Test RTMP with FFmpeg
```bash
# Push a test stream
ffmpeg -re -i test.mp4 -c copy -f flv rtmp://localhost/live/test

# Then view at: http://localhost:8080/live/test.m3u8
```

## Port Reference

| Port | Protocol | Purpose |
|------|----------|---------|
| 1935 | RTMP | Video stream input |
| 1985 | HTTP | SRS API |
| 8080 | HTTP | HLS output & Web UI |

## Configuration

The scripts use default SRS configuration. For custom configuration:

1. Create a custom `srs.conf` file
2. Modify `scripts/start-srs.sh` to mount the config:
   ```bash
   docker run -d \
     -p 1935:1935 -p 1985:1985 -p 8080:8080 \
     -v $(pwd)/srs.conf:/usr/local/srs/conf/srs.conf \
     --name srs \
     ossrs/srs:5
   ```

## Additional Resources

- [SRS Official Documentation](https://ossrs.io/)
- [SRS Docker Hub](https://hub.docker.com/r/ossrs/srs)
- [FFmpeg RTMP Documentation](https://trac.ffmpeg.org/wiki/StreamingGuide)

