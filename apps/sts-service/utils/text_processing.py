#!/usr/bin/env python3
"""
Text Processing Utilities for Multilingual TTS

This module contains all text preprocessing functions used for improving
translation quality and TTS synthesis.

Author: Philip Baillargeon (Assistance by Cursor/GPT)
"""

import re
from typing import Dict, List, Tuple


def convert_numbers_to_english_words(text: str) -> str:
    """
    Convert numbers to English words for better translation by M2M100
    
    Args:
        text: Text containing numbers
        
    Returns:
        Text with numbers converted to English words
    """
    try:
        import inflect
        p = inflect.engine()
        
        # Handle time expressions with following text (e.g., "1:54 REMAINING" -> "one minutes fifty-four seconds remaining")
        time_pattern = r'\b(\d{1,2}):(\d{2})\s+([A-Z\s]+)'
        def replace_time(match):
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            following_text = match.group(3).strip().lower()  # Convert following text to lowercase
            
            if minutes == 0:
                time_part = f'{p.number_to_words(seconds)} seconds'
            elif seconds == 0:
                time_part = f'{p.number_to_words(minutes)} minutes'
            else:
                time_part = f'{p.number_to_words(minutes)} minutes {p.number_to_words(seconds)} seconds'
            
            return f'{time_part} {following_text}'
        
        text = re.sub(time_pattern, replace_time, text)
        
        # Convert remaining numbers to words
        text = re.sub(r'\b(\d+)\b', lambda m: p.number_to_words(int(m.group(1))), text)
        
        return text
    except ImportError:
        # Fallback: simple number to word conversion
        number_words = {
            '0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four',
            '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine',
            '10': 'ten', '11': 'eleven', '12': 'twelve', '13': 'thirteen',
            '14': 'fourteen', '15': 'fifteen', '16': 'sixteen', '17': 'seventeen',
            '18': 'eighteen', '19': 'nineteen', '20': 'twenty'
        }
        
        for num, word in number_words.items():
            text = re.sub(r'\b' + num + r'\b', word, text)
        
        return text

def preprocess_text_for_translation(text: str) -> str:
    """
    Preprocess text for translation while preserving numerals to avoid translation errors
    
    Args:
        text: Input text
        
    Returns:
        Preprocessed text with numerals preserved
    """
    # Only handle time expressions and abbreviations, but preserve numerals
    try:
        import inflect
        p = inflect.engine()
        
        # Handle time expressions with following text (e.g., "1:54 REMAINING" -> "1:54 remaining")
        time_pattern = r'\b(\d{1,2}):(\d{2})\s+([A-Z\s]+)'
        def replace_time(match):
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            following_text = match.group(3).strip().lower()  # Convert following text to lowercase
            
            return f'{minutes}:{seconds} {following_text}'
        
        text = re.sub(time_pattern, replace_time, text)
        
        # Handle other preprocessing but preserve numerals
        # Remove hyphens for better translation (e.g., "TEN-YARD" -> "TEN YARD")
        text = text.replace('-', ' ')
        text = handle_abbreviations(text)
        
        return text
    except ImportError:
        # Fallback: minimal preprocessing
        text = text.replace('-', ' ')
        text = handle_abbreviations(text)
        return text

def handle_abbreviations(text: str) -> str:
    """
    Handle common abbreviations and special cases for better TTS pronunciation
    
    Args:
        text: Text containing abbreviations
        
    Returns:
        Text with abbreviations expanded
    """
    abbreviations = {
        'Eagles': 'Eagles',
        'Hawks': 'Hawks', 
        'NBA': 'N B A',
        'NFL': 'N F L',
        'MLB': 'M L B',
        'NHL': 'N H L',
        'vs': 'versus',
        'vs.': 'versus',
        '&': 'and',
        '%': 'percent',
        '$': 'dollars',
        '#': 'number',
        '@': 'at',
        '+': 'plus',
        '=': 'equals',
        '/': 'slash',
        '\\': 'backslash',
        '*': 'asterisk',
        '...': '...',  # Keep ellipsis as is
        '..': '..',    # Keep double dots as is
    }
    
    for abbrev, replacement in abbreviations.items():
        text = text.replace(abbrev, replacement)
    
    return text


def clean_punctuation(text: str) -> str:
    """
    Clean punctuation for better TTS pronunciation
    
    Args:
        text: Text with potentially problematic punctuation
        
    Returns:
        Text with cleaned punctuation
    """
    # Replace problematic punctuation
    replacements = {
        '¡': '',  # Remove inverted exclamation
        '¿': '',  # Remove inverted question
        '"': '"',  # Replace smart quotes with regular quotes
        '"': '"',
        ''': "'",  # Replace smart apostrophes
        ''': "'",
        '–': '-',  # Replace en dash with hyphen
        '—': '-',  # Replace em dash with hyphen
        '…': '...',  # Replace ellipsis with three dots
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Handle specific punctuation patterns for TTS
    # Don't modify ellipsis - keep as is for natural pause
    # Only convert double dots that are NOT part of ellipsis
    text = re.sub(r'(?<!\.)\.\.(?!\.)', ' .. ', text)  # Double dots not part of ellipsis
    # Don't convert all hyphens to "minus" - only in score contexts
    text = re.sub(r'(\d+)-(\d+)', r'\1 to \2', text)  # Scores like "15-12" -> "15 to 12"
    
    # Remove excessive punctuation
    text = re.sub(r'[!]{2,}', '!', text)  # Multiple exclamations to single
    text = re.sub(r'[?]{2,}', '?', text)  # Multiple questions to single
    text = re.sub(r'[.]{4,}', '...', text)  # Multiple dots to ellipsis
    
    # Clean up extra spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def preprocess_text_for_tts(text: str, convert_numbers: bool = True) -> str:
    """
    Preprocess text to handle special characters and improve TTS quality
    
    Args:
        text: Raw text to preprocess
        convert_numbers: Whether to convert numbers to English words for better translation
        
    Returns:
        Preprocessed text optimized for TTS synthesis
    """
    # Convert numbers to English words if requested (for better translation)
    if convert_numbers:
        text = convert_numbers_to_english_words(text)
    
    # Remove hyphens for better translation (e.g., "TEN-YARD" -> "TEN YARD")
    text = text.replace('-', ' ')
    
    # Handle common abbreviations and special cases
    text = handle_abbreviations(text)
    
    # Clean up punctuation for better TTS
    text = clean_punctuation(text)
    
    return text


def clean_speaker_prefix(text: str, speaker: str) -> str:
    """
    Remove speaker prefix from text for cleaner TTS input
    
    Args:
        text: Text with potential speaker prefix
        speaker: Detected speaker name
        
    Returns:
        Text with speaker prefix removed
    """
    # Remove speaker prefix patterns: "SPEAKER:" or "SPEAKER "
    pattern = rf'^{re.escape(speaker)}:?\s*'
    cleaned_text = re.sub(pattern, '', text).strip()
    
    return cleaned_text


def detect_speaker(text: str) -> str:
    """
    Detect speaker from text patterns - look for actual speaker labels
    
    Args:
        text: Text line to analyze for speaker
        
    Returns:
        Detected speaker name or 'default' if none found
    """
    # Look for explicit speaker labels like "Referee:", "Joe:", etc.
    speaker_match = re.match(r'^([A-Z][a-z]+):\s*', text)
    if speaker_match:
        speaker_name = speaker_match.group(1).strip()
        return speaker_name
    
    # Look for common speaker patterns in sports commentary
    if re.match(r'^>>\s*([A-Z][a-z]+):', text):
        speaker_match = re.match(r'^>>\s*([A-Z][a-z]+):', text)
        speaker_name = speaker_match.group(1).strip()
        return speaker_name
    
    # If no speaker name found, return default
    return 'default'
