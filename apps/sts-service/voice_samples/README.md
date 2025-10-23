# Voice Samples Directory

This directory contains voice samples for XTTS-v2 voice cloning.

## Requirements:
- Audio files should be 3-30 seconds long
- Mono audio is preferred (will be converted automatically)
- Sample rate of 22050 Hz is optimal
- Supported formats: WAV, MP3, FLAC, M4A

## Usage:
1. Place voice samples in this directory
2. Update coqui-voices.yaml to reference the voice samples:
   ```yaml
   speakers:
     JOE:
       speaker: "Andrew Chipper"  # Fallback voice
       voice_sample: "./voice_samples/joe_sample.wav"
   ```

## File naming convention:
- joe_sample.wav - Voice sample for JOE speaker
- referee_sample.wav - Voice sample for REFEREE speaker
- [speaker_name]_sample.wav - Voice sample for [speaker_name] speaker
