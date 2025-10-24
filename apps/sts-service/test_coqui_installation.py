#!/usr/bin/env python3
"""
Test script to verify Coqui TTS installation and dependencies
"""

import sys

def test_imports():
    """Test if all required packages can be imported"""
    print("Testing imports...")
    
    tests = [
        ("numpy", "NumPy"),
        ("torch", "PyTorch"),
        ("transformers", "Transformers"),
        ("TTS.api", "Coqui TTS"),
        ("soundfile", "SoundFile"),
        ("sounddevice", "SoundDevice"),
        ("yaml", "PyYAML"),
    ]
    
    failed = []
    for module, name in tests:
        try:
            if module == "TTS.api":
                exec(f"from {module} import TTS")
            else:
                exec(f"import {module}")
            
            # Get version if available
            try:
                version = eval(f"{module.split('.')[0]}.__version__")
                print(f"✓ {name}: {version}")
            except:
                print(f"✓ {name}: installed")
        except Exception as e:
            print(f"✗ {name}: {e}")
            failed.append(name)
    
    return len(failed) == 0, failed

def test_numpy_version():
    """Check if NumPy version is compatible"""
    print("\nChecking NumPy version...")
    try:
        import numpy as np
        version = np.__version__
        major_version = int(version.split('.')[0])
        
        if major_version >= 2:
            print(f"✗ NumPy {version} detected - Coqui TTS requires NumPy 1.x")
            print("  Run: pip install 'numpy<2.0.0' --force-reinstall")
            return False
        else:
            print(f"✓ NumPy {version} is compatible")
            return True
    except Exception as e:
        print(f"✗ Failed to check NumPy: {e}")
        return False

def test_coqui_tts():
    """Test if Coqui TTS can load a model"""
    print("\nTesting Coqui TTS model loading...")
    try:
        from TTS.api import TTS
        print("  Loading a simple model (this may take a moment)...")
        
        # Try to load a lightweight model
        tts = TTS(model_name='tts_models/en/ljspeech/tacotron2-DDC', progress_bar=False)
        print("✓ Coqui TTS model loaded successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to load Coqui TTS model: {e}")
        return False

def test_transformers():
    """Test if transformers is working"""
    print("\nTesting Transformers...")
    try:
        from transformers import __version__
        version = __version__
        major, minor = map(int, version.split('.')[:2])
        
        if (major == 4 and 33 <= minor < 41) or major < 4:
            print(f"✓ Transformers {version} is compatible with Coqui TTS")
            return True
        else:
            print(f"⚠️  Transformers {version} may not be compatible (recommended: 4.33-4.40)")
            return True  # Don't fail, just warn
    except Exception as e:
        print(f"✗ Failed to check Transformers: {e}")
        return False

def main():
    print("=" * 60)
    print("Coqui TTS Installation Test")
    print("=" * 60)
    
    all_passed = True
    
    # Test 1: Imports
    imports_ok, failed_imports = test_imports()
    if not imports_ok:
        print(f"\n⚠️  Some imports failed: {', '.join(failed_imports)}")
        all_passed = False
    
    # Test 2: NumPy version
    if not test_numpy_version():
        all_passed = False
    
    # Test 3: Transformers version
    if not test_transformers():
        all_passed = False
    
    # Test 4: Coqui TTS (only if other tests passed)
    if all_passed:
        if not test_coqui_tts():
            all_passed = False
    else:
        print("\n⚠️  Skipping Coqui TTS test due to previous failures")
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All tests passed! Your installation is ready.")
        print("\nYou can now run:")
        print("  python talk_multi_coqui.py")
        print("  python stream_audio_client.py")
    else:
        print("❌ Some tests failed. Please fix the issues above.")
        print("\nQuick fix:")
        print("  bash fix_coqui_installation.sh")
    print("=" * 60)
    
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()

