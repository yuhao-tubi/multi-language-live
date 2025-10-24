# Tubi EPG API - Quick Start Guide

## ✅ What Was Built

I've successfully integrated the Tubi EPG Programming API into your Live Media Service:

### 🔧 Backend Components

1. **Authentication Service** (`tubi-auth.service.ts`)
   - Anonymous token generation with HMAC-SHA256 signing
   - Automatic token caching (refreshes 5 min before expiration)
   - Code verifier/challenge generation

2. **EPG Service** (`tubi-epg.service.ts`)
   - Fetches programming data from Tubi EPG CDN
   - Extracts manifest URLs from responses
   - Helper functions for video resource details

3. **API Endpoints** (added to `main.ts`)
   - `GET /api/tubi/manifest?contentId={id}` - Full details
   - `GET /api/tubi/manifest/quick?contentId={id}` - URL only
   - `POST /api/tubi/clear-cache` - Clear token cache

### 🎨 Frontend UI

Added a **"📺 Tubi EPG - Get Manifest URL"** panel to the web interface:
- Content ID input field
- Fetch button with loading state
- Result display with video metadata
- Auto-populates Pipeline Source URL field
- Activity log integration

---

## 🚀 How to Use

### Via Web UI (Easiest)

1. **Open the control panel:**
   ```
   http://localhost:3000
   ```

2. **In the "Tubi EPG" panel:**
   - Enter a Tubi Content ID
   - Click "🔍 Fetch Manifest URL"
   - View the manifest URL and video details

3. **Use the manifest URL:**
   - It's automatically copied to the "HLS Source URL" field
   - Click "▶️ Start Pipeline" to process the stream

### Via API

**Get full details:**
```bash
curl "http://localhost:3000/api/tubi/manifest?contentId=YOUR_CONTENT_ID" | jq
```

**Get URL only:**
```bash
curl "http://localhost:3000/api/tubi/manifest/quick?contentId=YOUR_CONTENT_ID"
```

**Clear token cache:**
```bash
curl -X POST http://localhost:3000/api/tubi/clear-cache
```

---

## 📝 Getting Valid Content IDs

To test with real Tubi content:

1. **From Tubi Web/App:**
   - Browse to any Tubi video
   - Check the URL or network requests for content IDs
   - Content IDs are typically numeric (e.g., "400000157")

2. **From Network Inspector:**
   - Open browser DevTools → Network tab
   - Play a video on Tubi
   - Look for `/content/epg/programming` requests
   - Extract the `content_id` parameter

3. **Example Content ID Format:**
   - Usually 9-digit numbers: `400000157`
   - May vary based on content type

---

## 🔍 Testing the Integration

### 1. Check Service Health
```bash
curl http://localhost:3000/api/health
```

### 2. Test with Your Content ID
```bash
# Replace YOUR_CONTENT_ID with a real Tubi content ID
curl "http://localhost:3000/api/tubi/manifest?contentId=YOUR_CONTENT_ID" | jq
```

### 3. Expected Response
```json
{
  "success": true,
  "manifestUrl": "https://link.theplatform.com/s/dJ5BDC/...",
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

---

## 📂 Files Created/Modified

### New Files
- `src/services/tubi-auth.service.ts` - Authentication logic
- `src/services/tubi-epg.service.ts` - EPG API client
- `docs/TUBI_EPG_API.md` - Full documentation
- `TUBI_EPG_QUICKSTART.md` - This file

### Modified Files
- `src/main.ts` - Added 3 new API endpoints
- `public/index.html` - Added Tubi EPG UI panel

---

## 🎯 Key Features

✅ **Anonymous Authentication** - No user account required  
✅ **Token Caching** - Efficient, automatic token reuse  
✅ **Error Handling** - Graceful failures with error messages  
✅ **Lazy Logger** - Fixed initialization order issues  
✅ **Clean UI** - Simple, intuitive interface  
✅ **Auto-populate** - Manifest URL copies to pipeline field  

---

## 🐛 Troubleshooting

### "Failed to fetch EPG programming data"

**Possible causes:**
1. Invalid or unavailable content ID
2. Content not available in your region
3. Tubi API rate limiting
4. Network issues

**Solutions:**
- Try a different, known-valid content ID
- Check Tubi's platform for available content
- Clear token cache: `POST /api/tubi/clear-cache`
- Check service logs for detailed errors

### "Logger not initialized" Error

**Status:** ✅ Fixed  
The services now use lazy logger initialization to avoid module load order issues.

---

## 📖 Documentation

For complete documentation, see:
- **`docs/TUBI_EPG_API.md`** - Full API reference
- **Your original guide** - Tubi EPG Programming API specifications

---

## 🎉 Next Steps

1. **Get valid Tubi content IDs** from Tubi's platform
2. **Test the API** with real content IDs
3. **Use manifest URLs** in your media pipeline
4. **Integrate with other services** (STS, audio processing, etc.)

---

## 💡 Usage Example

Complete workflow:

```bash
# 1. Fetch manifest URL
MANIFEST=$(curl -s "http://localhost:3000/api/tubi/manifest/quick?contentId=YOUR_ID" | jq -r '.manifestUrl')

# 2. Start pipeline with Tubi stream
curl -X POST http://localhost:3000/api/pipeline/start \
  -H "Content-Type: application/json" \
  -d "{
    \"sourceUrl\": \"$MANIFEST\",
    \"streamId\": \"tubi-stream\",
    \"bufferDuration\": 30
  }"

# 3. Check pipeline status
curl http://localhost:3000/api/pipeline/status | jq
```

---

**Built:** 2025-10-24  
**Service:** Live Media Service  
**Port:** http://localhost:3000  
**Status:** ✅ Running and ready to use!

