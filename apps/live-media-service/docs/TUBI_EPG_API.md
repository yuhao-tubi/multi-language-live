# Tubi EPG Programming API Integration

This document describes how to use the Tubi EPG (Electronic Program Guide) API integration in the Live Media Service.

## Overview

The Tubi EPG API integration allows you to fetch video manifest URLs from Tubi's content catalog. This is useful for:

- Getting live stream URLs for Tubi content
- Retrieving video metadata (resolution, codec, duration)
- Integrating Tubi streams into your media pipeline

## Features

✅ **Anonymous Authentication** - Automatic token generation with caching  
✅ **Manifest URL Extraction** - Get HLS/DASH stream URLs  
✅ **Video Metadata** - Resolution, codec, and duration information  
✅ **Token Caching** - Efficient token reuse (auto-refresh before expiration)  
✅ **Web UI Integration** - Simple button interface to fetch manifests

---

## API Endpoints

### 1. Get EPG Manifest (Full Details)

```http
GET /api/tubi/manifest?contentId={contentId}
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `contentId` | string | ✅ Yes | Tubi content ID (e.g., "400000157") |
| `platform` | string | No | Platform identifier (default: "amazon") |
| `deviceId` | string | No | Device UUID (auto-generated if not provided) |
| `limitResolutions` | string | No | Comma-separated resolutions (e.g., "h264_1080p,h265_1080p") |

**Example Request:**

```bash
curl http://localhost:3000/api/tubi/manifest?contentId=400000157
```

**Example Response:**

```json
{
  "success": true,
  "manifestUrl": "https://link.theplatform.com/s/dJ5BDC/media/guid/2389906296/12345678?formats=m3u&format=redirect",
  "videoResource": {
    "type": "hlsv6_widevine",
    "resolution": "1080p",
    "codec": "h264",
    "duration": 7200
  },
  "contentInfo": {
    "contentId": "400000157",
    "title": "Content Title"
  }
}
```

### 2. Quick Manifest Fetch (URL Only)

```http
GET /api/tubi/manifest/quick?contentId={contentId}
```

**Example Request:**

```bash
curl http://localhost:3000/api/tubi/manifest/quick?contentId=400000157
```

**Example Response:**

```json
{
  "success": true,
  "manifestUrl": "https://link.theplatform.com/s/dJ5BDC/media/guid/2389906296/12345678?formats=m3u&format=redirect"
}
```

### 3. Clear Token Cache

```http
POST /api/tubi/clear-cache
```

Clears the cached Tubi authentication token (useful for testing or error recovery).

**Example Request:**

```bash
curl -X POST http://localhost:3000/api/tubi/clear-cache
```

---

## Web UI Usage

### Step 1: Open the Control Panel

Navigate to: `http://localhost:3000`

### Step 2: Use the Tubi EPG Panel

1. Enter a Tubi Content ID (e.g., `400000157`)
2. Click **"🔍 Fetch Manifest URL"**
3. The manifest URL will be displayed with video details
4. The URL is automatically copied to the "HLS Source URL" field

### Step 3: Start Pipeline (Optional)

After fetching the manifest URL, you can:
- Click **"▶️ Start Pipeline"** to process the stream
- The manifest URL is already populated in the source field

---

## Code Examples

### TypeScript/Node.js

```typescript
// Fetch manifest URL
const response = await fetch('http://localhost:3000/api/tubi/manifest?contentId=400000157');
const data = await response.json();

if (data.success) {
  console.log('Manifest URL:', data.manifestUrl);
  console.log('Resolution:', data.videoResource.resolution);
  console.log('Duration:', data.videoResource.duration);
}
```

### cURL

```bash
# Full details
curl "http://localhost:3000/api/tubi/manifest?contentId=400000157"

# Quick fetch (URL only)
curl "http://localhost:3000/api/tubi/manifest/quick?contentId=400000157"

# With custom platform
curl "http://localhost:3000/api/tubi/manifest?contentId=400000157&platform=web"
```

### Python

```python
import requests

# Fetch manifest
response = requests.get('http://localhost:3000/api/tubi/manifest', params={
    'contentId': '400000157'
})

data = response.json()
if data['success']:
    manifest_url = data['manifestUrl']
    print(f"Manifest URL: {manifest_url}")
```

---

## Architecture

### Authentication Flow

```
┌──────────────────────┐
│ 1. Get Signing Key   │
│    (code challenge)  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 2. Request Token     │
│    (signed request)  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 3. Cache Token       │
│    (5 min buffer)    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 4. Call EPG API      │
│    (Bearer token)    │
└──────────────────────┘
```

### Components

1. **`tubi-auth.service.ts`** - Handles anonymous authentication
   - Generates code verifier/challenge
   - Requests signing keys
   - Manages token lifecycle
   - Implements token caching

2. **`tubi-epg.service.ts`** - Fetches EPG programming data
   - Calls EPG API with authentication
   - Extracts manifest URLs
   - Provides helper functions

3. **API Endpoints (main.ts)** - REST API integration
   - `/api/tubi/manifest` - Full details
   - `/api/tubi/manifest/quick` - Quick fetch
   - `/api/tubi/clear-cache` - Cache management

4. **Web UI (index.html)** - User interface
   - Content ID input
   - Fetch button
   - Result display
   - Auto-populate pipeline source

---

## Configuration

### Default Values

```typescript
const DEFAULT_PLATFORM = 'amazon';
const DEFAULT_DEVICE_ID = '5304f5df-5052-4edc-8087-c0988bd8ae10';
```

### Token Caching

- Tokens are cached automatically
- Cache expires 5 minutes before token expiration
- Tokens are valid for ~1 hour

---

## Error Handling

### Common Errors

**1. Invalid Content ID**

```json
{
  "success": false,
  "error": "Failed to fetch EPG programming data"
}
```

**Solution:** Verify the content ID is correct and content is available.

**2. Authentication Failed**

```json
{
  "success": false,
  "error": "Failed to get Tubi access token"
}
```

**Solution:** Clear token cache and retry:
```bash
curl -X POST http://localhost:3000/api/tubi/clear-cache
```

**3. No Manifest URL Found**

```json
{
  "success": false,
  "error": "No manifest URL found in programming data"
}
```

**Solution:** Content may not have video streams available or may be restricted.

---

## Testing

### Test Content IDs

Try these Tubi content IDs for testing:

- `400000157` - Sample content (used in examples)
- Use real Tubi content IDs from the Tubi platform

### Test Commands

```bash
# Test full API
curl "http://localhost:3000/api/tubi/manifest?contentId=400000157" | jq

# Test quick fetch
curl "http://localhost:3000/api/tubi/manifest/quick?contentId=400000157" | jq '.manifestUrl'

# Test token cache clearing
curl -X POST http://localhost:3000/api/tubi/clear-cache
```

---

## Troubleshooting

### Issue: Logger Not Initialized Error

**Error:**
```
Error: Logger not initialized. Call initLogger() first.
```

**Solution:** This has been fixed by using lazy logger initialization. If you still see this, ensure you're using the latest code.

### Issue: Token Expired

**Solution:** Tokens are automatically refreshed. If you encounter issues, clear the cache:

```bash
curl -X POST http://localhost:3000/api/tubi/clear-cache
```

### Issue: CORS Errors

If calling from a browser, ensure the API is running on the same origin or configure CORS in `main.ts`.

---

## Integration with Pipeline

After fetching a manifest URL, you can use it directly in the media pipeline:

1. **Fetch Manifest:**
   ```bash
   MANIFEST=$(curl -s "http://localhost:3000/api/tubi/manifest/quick?contentId=400000157" | jq -r '.manifestUrl')
   ```

2. **Start Pipeline:**
   ```bash
   curl -X POST http://localhost:3000/api/pipeline/start \
     -H "Content-Type: application/json" \
     -d "{\"sourceUrl\": \"$MANIFEST\", \"streamId\": \"tubi-stream\"}"
   ```

3. **Or use the Web UI:**
   - The manifest URL is auto-populated in the source field
   - Just click "Start Pipeline"

---

## API Reference

See the original guide for detailed API documentation:
- Authentication flow details
- Query parameter specifications
- Response structure
- TypeScript interfaces

---

## Security Notes

⚠️ **Anonymous Authentication Only**

This integration uses anonymous (guest) authentication. Features requiring user accounts are not supported.

⚠️ **Token Storage**

Tokens are cached in memory only and are not persisted to disk.

⚠️ **Rate Limiting**

Be mindful of Tubi's API rate limits. Token caching helps minimize authentication requests.

---

## Future Enhancements

Potential improvements:
- [ ] Support for authenticated users
- [ ] Multiple resolution selection
- [ ] Content search/discovery
- [ ] Persistent token storage
- [ ] Retry logic with exponential backoff
- [ ] Metrics and analytics

---

**Last Updated:** 2025-10-24  
**Version:** 1.0.0  
**Endpoints:** `/api/tubi/*`

