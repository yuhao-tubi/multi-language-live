"""
Utils package for multilingual TTS processing
"""

from .text_processing import (
    convert_numbers_to_english_words,
    handle_abbreviations,
    clean_punctuation,
    preprocess_text_for_tts,
    clean_speaker_prefix,
    detect_speaker,
)

__all__ = [
    'convert_numbers_to_english_words', 
    'handle_abbreviations',
    'clean_punctuation',
    'preprocess_text_for_tts',
    'clean_speaker_prefix',
    'detect_speaker',
]
