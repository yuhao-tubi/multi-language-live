# Live Caption Test - Setup Instructions

This repository provides multilingual text-to-speech with speaker detection and adaptive speed control for VTT files.

## Dependencies

### ⚠️ System Dependencies (Install First!)

**rubberband-cli** (REQUIRED for audio speed adjustment):
- **macOS**: `brew install rubberband`
- **Ubuntu/Debian**: `sudo apt-get install rubberband-cli`
- **CentOS/RHEL**: `sudo yum install rubberband-cli`
- **Windows**: Download from https://breakfastquay.com/rubberband/
- **From source**: https://github.com/breakfastquay/rubberband

> **Note**: This must be installed BEFORE creating the Python environment, as it's a system-level dependency.

### Python Dependencies

- **Python 3.10+** (required for Coqui TTS compatibility)
- PyTorch
- Coqui TTS
- Transformers (M2M100)
- Audio processing libraries (sounddevice, soundfile)

#### Option 1: Conda Environment (Recommended)

```bash
# Create and activate conda environment
conda env create -f environment.yml
conda activate live-caption-test
```

The conda environment will install core packages (PyTorch, transformers, etc.) via conda and specialized packages via pip automatically.

> **Note**: This uses a hybrid approach - conda for core ML packages and pip for specialized audio/NLP packages that aren't available in conda channels.

#### Option 2: Pip Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Main Application
```bash
# Interactive mode
python talk_multi_coqui.py

# Process VTT file
python talk_multi_coqui.py --vtt sample_vtt_files/livestream_sample.vtt

# With adaptive speed control
python talk_multi_coqui.py --vtt sample_vtt_files/livestream_sample.vtt --adaptive-speed
```

### Translation Testing
```bash
# Test specific phrases
python test_translation.py "TEN-YARD penalty"
python test_translation.py "NOW 1:54 REMAINING"

# Interactive testing mode
python test_translation.py --interactive
```

## Configuration

Edit `coqui-voices.yaml` to configure TTS models and voices for different languages.

## Features

- **Multilingual Translation**: Uses M2M100 model for high-quality translation
- **Speaker Detection**: Automatically detects speakers from VTT files
- **Adaptive Speed Control**: Adjusts TTS speed to match VTT timing
- **High-Quality Audio**: Uses rubberband for professional audio processing
- **Caching**: Caches translations and audio for improved performance
- **Text Preprocessing**: Handles hyphenated words, time expressions, and abbreviations

## Troubleshooting

### Common Issues

1. **rubberband not found**: Install rubberband-cli system package first (see System Dependencies above)
2. **CUDA/GPU Issues**: The script automatically falls back to CPU/MPS if CUDA is not available
3. **Audio Device Issues**: Check your audio device settings if playback fails
4. **Model Download**: First run will download M2M100 and TTS models (several GB)
5. **Memory Usage**: Large models require significant RAM (8GB+ recommended)

### Coqui TTS Installation Issues

#### Error: "issubclass() arg 1 must be a class"

This error indicates a NumPy version incompatibility. Coqui TTS 0.24.1 requires NumPy 1.x.

**Solution:**
```bash
# Remove existing environment
conda deactivate
conda env remove -n multilingual-tts

# Recreate environment with updated dependencies
conda env create -f environment.yml
conda activate multilingual-tts

# Verify NumPy version (should be < 2.0.0)
python -c "import numpy; print(f'NumPy version: {numpy.__version__}')"

# Verify Coqui TTS installation
python -c "from TTS.api import TTS; print('Coqui TTS loaded successfully')"
```

#### Other Dependency Issues

If you continue to have issues after fixing NumPy:

```bash
# Check for conflicting packages
pip list | grep -E "numpy|torch|transformers|TTS"

# Force reinstall Coqui TTS
pip uninstall coqui-tts -y
pip install coqui-tts==0.24.1

# If still failing, try installing dependencies in order
pip install "numpy<2.0.0"
pip install torch torchaudio
pip install "transformers>=4.33.0,<4.41.0"
pip install coqui-tts==0.24.1
```

### Performance Tips

- Use `--no-cache` to disable caching during development
- Enable `--adaptive-speed` for VTT files to match timing exactly
- Close other applications to free up memory for large models
