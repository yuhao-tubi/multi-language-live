#!/usr/bin/env python3
"""
Translation Testing Helper Script

This script uses the same translation preprocessing and M2M100 model as the main script,
but only performs translation without TTS synthesis - perfect for testing preprocessing fixes.

Usage:
    python test_translation.py "TEN-YARD penalty"
    python test_translation.py "NOW 1:54 REMAINING"
    python test_translation.py --interactive
"""

import json
import time
import hashlib
from pathlib import Path
from typing import Dict, Tuple
from rich.console import Console

# Offline MT (multilingual translation)
import torch
from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

# Initialize console and cache directory
console = Console()
CACHE_DIR = Path(".cache_coqui")
CACHE_DIR.mkdir(exist_ok=True)
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"

# Import text processing functions from utils module
from utils.text_processing import (
    convert_numbers_to_english_words,
    handle_abbreviations,
    clean_punctuation,
    preprocess_text_for_tts,
    preprocess_text_for_translation,
)

# =============================================================================
# TRANSLATION FUNCTIONS (copied from main script)
# =============================================================================

def sha1(*parts: str) -> str:
    """Generate SHA1 hash from multiple string parts"""
    h = hashlib.sha1()
    for p in parts: 
        h.update(p.encode("utf-8"))
    return h.hexdigest()

# Global cache for MT model
_mt_cache = {}

def get_mt() -> Tuple[M2M100ForConditionalGeneration, M2M100Tokenizer]:
    """Get or load multilingual translation model"""
    if "mt" not in _mt_cache:
        console.print("Loading multilingual MT (M2M100 418M)…")
        model = M2M100ForConditionalGeneration.from_pretrained("facebook/m2m100_418M")
        tokenizer = M2M100Tokenizer.from_pretrained("facebook/m2m100_418M")
        _mt_cache["mt"] = (model, tokenizer)
    return _mt_cache["mt"]

def translate(text: str, tgt: str) -> Dict[str, str]:
    """
    Translate text to target language
    
    Args:
        text: Text to translate
        tgt: Target language code
        
    Returns:
        Dictionary with translation result and source language
    """
    model, tokenizer = get_mt()
    
    # Assume source language is always English
    src = "en"
    
    # Set source and target languages
    tokenizer.src_lang = src
    inputs = tokenizer(text, return_tensors="pt")
    
    # Generate translation with TTS-friendly parameters
    with torch.no_grad():
        generated_tokens = model.generate(
            **inputs, 
            forced_bos_token_id=tokenizer.get_lang_id(tgt),
            num_beams=4,  # Use beam search for more accurate translation
            early_stopping=True,  # Stop when EOS token is generated
            repetition_penalty=1.1,  # Slight penalty to avoid repetition
            max_length=100,  # Reasonable max length for TTS
            do_sample=False  # Use deterministic generation
        )
    
    result = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]
    return {"out": result, "src": src}

# =============================================================================
# TESTING FUNCTIONS
# =============================================================================

def test_translation(text: str, target_lang: str = "es", use_cache: bool = True) -> Dict[str, str]:
    """
    Test translation with preprocessing
    
    Args:
        text: Original text to translate
        target_lang: Target language code
        use_cache: Whether to use translation cache
        
    Returns:
        Dictionary with original, preprocessed, and translated text
    """
    console.print(f"[bold]Original text:[/bold] {text}")
    
    # Preprocess text (same as main script)
    preprocessed_text = preprocess_text_for_translation(text)
    console.print(f"[bold]Preprocessed:[/bold] {preprocessed_text}")
    
    # Translate with cache
    t0 = time.time()
    if use_cache:
        mt_key = sha1("MT", preprocessed_text, target_lang)
        mt_path = CACHE_DIR / f"{mt_key}.json"
        if mt_path.exists():
            mt_res = json.loads(mt_path.read_text("utf-8"))
            console.print(f"[dim]Using cached translation[/dim]")
        else:
            mt_res = translate(preprocessed_text, target_lang)
            mt_path.write_text(json.dumps(mt_res, ensure_ascii=False), encoding="utf-8")
    else:
        mt_res = translate(preprocessed_text, target_lang)
    
    t1 = time.time()
    
    console.print(f"[bold]{target_lang.upper()}:[/bold] {mt_res['out']}  [dim](MT {t1-t0:.2f}s; src={mt_res['src']})[/dim]")
    
    return {
        "original": text,
        "preprocessed": preprocessed_text,
        "translated": mt_res['out'],
        "source_lang": mt_res['src'],
        "target_lang": target_lang,
        "translation_time": t1 - t0
    }

def interactive_mode():
    """Run interactive translation testing mode"""
    console.print("[green]Translation Testing Mode[/green]")
    console.print("Type text to test translation preprocessing and results.")
    console.print("Commands: 'quit' to exit, 'clear' to clear cache\n")
    
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line: 
            continue
        if line.lower() in ("q", "quit", "exit"): 
            break
        if line.lower() == "clear":
            # Clear cache
            cache_files = list(CACHE_DIR.glob("*.json"))
            for f in cache_files:
                f.unlink()
            console.print(f"[yellow]Cleared {len(cache_files)} cached translations[/yellow]")
            continue
        
        console.print()
        test_translation(line)
        console.print()

# =============================================================================
# MAIN FUNCTION
# =============================================================================

def main():
    """Main entry point"""
    import argparse
    
    ap = argparse.ArgumentParser(description="Test translation preprocessing without TTS")
    ap.add_argument("text", nargs="?", help="Text to translate")
    ap.add_argument("--target", "-t", default="es", help="Target language (default: es)")
    ap.add_argument("--no-cache", action="store_true", help="Disable translation cache")
    ap.add_argument("--interactive", "-i", action="store_true", help="Run in interactive mode")
    args = ap.parse_args()
    
    if args.interactive:
        interactive_mode()
    elif args.text:
        test_translation(args.text, args.target, not args.no_cache)
    else:
        # Run some test cases
        console.print("[bold]Running test cases:[/bold]\n")
        
        test_cases = [
            "TEN-YARD penalty",
            "NOW 1:54 REMAINING", 
            "FIFTEEN-YARD line",
            "2:30 LEFT in the game",
            "TOUCH-DOWN scored",
            "FIRST-DOWN conversion"
        ]
        
        for test_text in test_cases:
            console.print(f"[bold]Test Case:[/bold] {test_text}")
            test_translation(test_text, args.target, not args.no_cache)
            console.print()

if __name__ == "__main__":
    main()
