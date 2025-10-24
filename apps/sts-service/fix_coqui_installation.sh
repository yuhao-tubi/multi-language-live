#!/bin/bash
# Quick fix script for Coqui TTS installation issues
# Addresses the "issubclass() arg 1 must be a class" error

set -e

echo "🔧 Coqui TTS Installation Fix Script"
echo "====================================="
echo ""

# Check if conda is available
if ! command -v conda &> /dev/null; then
    echo "❌ Error: conda not found. Please install Miniconda or Anaconda first."
    exit 1
fi

# Check if environment.yml exists
if [ ! -f "environment.yml" ]; then
    echo "❌ Error: environment.yml not found. Please run this script from the sts-service directory."
    exit 1
fi

# Get current conda environment name
CURRENT_ENV=$(conda info --envs | grep '*' | awk '{print $1}')
ENV_NAME="multilingual-tts"

echo "Step 1: Checking current environment..."
if [ "$CURRENT_ENV" == "$ENV_NAME" ]; then
    echo "⚠️  You are currently in the $ENV_NAME environment. Deactivating..."
    conda deactivate
fi

echo ""
echo "Step 2: Removing existing environment (if it exists)..."
if conda env list | grep -q "^$ENV_NAME "; then
    conda env remove -n $ENV_NAME -y
    echo "✓ Removed existing environment"
else
    echo "ℹ️  No existing environment found"
fi

echo ""
echo "Step 3: Creating fresh environment with fixed dependencies..."
conda env create -f environment.yml
echo "✓ Environment created"

echo ""
echo "Step 4: Activating environment and verifying installation..."
eval "$(conda shell.bash hook)"
conda activate $ENV_NAME

echo ""
echo "Verifying NumPy version..."
NUMPY_VERSION=$(python -c "import numpy; print(numpy.__version__)" 2>&1)
if [ $? -eq 0 ]; then
    echo "✓ NumPy version: $NUMPY_VERSION"
    if [[ "$NUMPY_VERSION" == 2.* ]]; then
        echo "❌ Warning: NumPy 2.x detected! This will cause issues."
        echo "   Forcing NumPy 1.x installation..."
        pip install "numpy<2.0.0" --force-reinstall
        NUMPY_VERSION=$(python -c "import numpy; print(numpy.__version__)")
        echo "✓ NumPy version after fix: $NUMPY_VERSION"
    fi
else
    echo "❌ Failed to check NumPy version"
fi

echo ""
echo "Verifying PyTorch..."
python -c "import torch; print(f'✓ PyTorch version: {torch.__version__}')" 2>&1 || echo "❌ PyTorch import failed"

echo ""
echo "Verifying Transformers..."
python -c "import transformers; print(f'✓ Transformers version: {transformers.__version__}')" 2>&1 || echo "❌ Transformers import failed"

echo ""
echo "Verifying Coqui TTS..."
python -c "from TTS.api import TTS; print('✓ Coqui TTS loaded successfully')" 2>&1 || {
    echo "❌ Coqui TTS failed to load"
    echo ""
    echo "Attempting manual reinstall..."
    pip uninstall coqui-tts -y
    pip install coqui-tts==0.24.1
    python -c "from TTS.api import TTS; print('✓ Coqui TTS loaded successfully after reinstall')"
}

echo ""
echo "Step 5: Testing model loading..."
python -c "
from TTS.api import TTS
print('Loading test model...')
tts = TTS(model_name='tts_models/en/ljspeech/tacotron2-DDC', progress_bar=False)
print('✓ Model loaded successfully!')
" 2>&1 || echo "⚠️  Model loading failed (this might be due to network issues, try running your script)"

echo ""
echo "====================================="
echo "✅ Installation fix complete!"
echo ""
echo "To activate the environment, run:"
echo "  conda activate $ENV_NAME"
echo ""
echo "To test your TTS setup, run:"
echo "  python test.py"
echo ""

