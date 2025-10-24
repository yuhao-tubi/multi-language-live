# Quick Installation Fix

## The Problem

Error: `issubclass() arg 1 must be a class`

**Cause:** Coqui TTS 0.24.1 is incompatible with NumPy 2.x

## The Solution

Run the automated fix script:

```bash
cd apps/sts-service
bash fix_coqui_installation.sh
```

This takes about 5-10 minutes and will:
1. ✓ Remove your existing conda environment
2. ✓ Recreate it with the correct NumPy version (<2.0.0)
3. ✓ Install all dependencies in the correct order
4. ✓ Verify that Coqui TTS can load successfully

## Verify Installation

After running the fix:

```bash
conda activate multilingual-tts
python test_coqui_installation.py
```

You should see:
```
✅ All tests passed! Your installation is ready.
```

## Quick Manual Fix (Alternative)

If you prefer to fix manually:

```bash
# 1. Deactivate current environment
conda deactivate

# 2. Remove existing environment
conda env remove -n multilingual-tts

# 3. Recreate environment (now includes NumPy <2.0.0 constraint)
conda env create -f environment.yml

# 4. Activate and test
conda activate multilingual-tts
python test_coqui_installation.py
```

## Still Having Issues?

See `TROUBLESHOOTING.md` for comprehensive troubleshooting steps, or run:

```bash
# Check what's installed
pip list | grep -E "numpy|torch|transformers|TTS"

# Verify versions
python -c "import numpy; print(f'NumPy: {numpy.__version__}')"
python -c "import transformers; print(f'Transformers: {transformers.__version__}')"
python -c "from TTS.api import TTS; print('Coqui TTS: OK')"
```

## After Fix is Complete

Run your applications normally:

```bash
# Interactive mode
python talk_multi_coqui.py

# Process VTT file
python talk_multi_coqui.py --vtt sample_vtt_files/livestream_sample.vtt

# Stream audio client
python stream_audio_client.py --config coqui-voices.yaml --targets es,zh
```

## Files Created/Updated

- `environment.yml` - Added NumPy <2.0.0 constraint
- `fix_coqui_installation.sh` - Automated fix script (NEW)
- `test_coqui_installation.py` - Installation test script (NEW)
- `SETUP.md` - Added troubleshooting section
- `TROUBLESHOOTING.md` - Comprehensive guide (NEW)
- `FIX_INSTALLATION.md` - This file (NEW)

