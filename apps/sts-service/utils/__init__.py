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

from .speaker_detection import (
    SpeakerDetector,
    create_speaker_detector,
)

__all__ = [
    'convert_numbers_to_english_words', 
    'handle_abbreviations',
    'clean_punctuation',
    'preprocess_text_for_tts',
    'clean_speaker_prefix',
    'detect_speaker',
    'SpeakerDetector',
    'create_speaker_detector',
]
