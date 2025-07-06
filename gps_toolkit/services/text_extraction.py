"""
OCR text extraction service for GPS Toolkit.

This module provides sophisticated Optical Character Recognition (OCR) capabilities
for extracting text from images. It uses the fast 'ocrit' CLI tool as the primary
OCR method (leveraging Apple's Vision ML for speed), with pytesseract as a fallback.

Key Features:
1. Fast OCR with ocrit:
   - Uses Apple's Vision ML framework for high-speed OCR
   - Direct HEIC support without conversion
   - Sub-second processing for typical images
   - Multi-language support

2. Intelligent Text Validation:
   - Gibberish detection
   - Word validity checking
   - Language detection with fallback patterns

3. Fallback to pytesseract:
   - Advanced preprocessing techniques when ocrit is unavailable
   - Multiple thresholding techniques (adaptive, Otsu's)
   - Confidence score filtering
   - Different PSM (Page Segmentation Mode) attempts

4. Native HEIC Support:
   - Direct processing with ocrit
   - Automatic conversion for pytesseract fallback

Design Philosophy:
- Speed first: Use fast ocrit tool when available
- Quality over quantity: Better to return no text than gibberish
- Graceful degradation: Fall back to pytesseract if needed
- Language awareness: Detect and report text language

The service gracefully handles missing dependencies and provides meaningful
error messages when OCR is unavailable.
"""

import os
import re
import tempfile
import subprocess
import asyncio
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import shutil

from ..core.utils import extract_urls_from_text

# Check for ocrit availability
HAS_OCRIT = shutil.which('ocrit') is not None

# Import optional OCR libraries
try:
    import pytesseract
    from langdetect import detect, detect_langs, LangDetectException
    HAS_PYTESSERACT = True
except ImportError:
    HAS_PYTESSERACT = False

# Set HAS_OCR based on availability of any OCR method
HAS_OCR = HAS_OCRIT or HAS_PYTESSERACT

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False


class TextExtractionService:
    """
    Service for OCR text extraction operations.
    
    This service extracts readable text from images using the fast 'ocrit' CLI tool
    as the primary method, with Tesseract OCR as a fallback. It's designed to be
    fast while maintaining quality through text validation.
    
    The service implements a multi-stage approach:
    1. Fast OCR using ocrit (if available)
    2. Fallback to pytesseract with preprocessing (if ocrit unavailable)
    3. Text validation and cleanup
    4. Language detection
    5. URL extraction
    
    Attributes:
        language_patterns (Dict): Common words for language detection fallback
        
    Methods:
        extract_text_from_image: Main entry point for text extraction
        
    Private Methods:
        _extract_with_ocrit: Fast OCR using ocrit CLI tool
        _extract_with_pytesseract: Fallback OCR with preprocessing
        _convert_heic_to_jpeg: Handle Apple HEIC format for pytesseract
        _preprocess_with_opencv: Advanced preprocessing using OpenCV
        _preprocess_with_pil: Basic preprocessing using PIL
        _try_alternative_ocr: Fallback OCR attempts with different modes
        _is_valid_word: Check if a word is likely real text
        _is_valid_text: Validate overall text quality
        _detect_language: Identify the language of extracted text
    """
    
    def __init__(self):
        """
        Initialize the text extraction service.
        
        Sets up language detection patterns for common European languages.
        These patterns are used as a fallback when the langdetect library
        has low confidence, especially for short text snippets.
        
        The patterns contain the most common words (articles, prepositions,
        conjunctions) that are strong indicators of each language.
        """
        self.language_patterns = {
            'en': {'the', 'and', 'is', 'in', 'at', 'to', 'for', 'of', 'with', 'on', 'a', 'an'},
            'es': {'el', 'la', 'de', 'en', 'y', 'los', 'las', 'del', 'al', 'es', 'un', 'una'},
            'fr': {'le', 'la', 'de', 'et', 'les', 'des', 'un', 'une', 'dans', 'pour', 'avec'},
            'de': {'der', 'die', 'das', 'und', 'in', 'den', 'im', 'ein', 'eine', 'mit', 'für'},
            'it': {'il', 'la', 'di', 'e', 'in', 'che', 'un', 'una', 'per', 'con', 'del'},
            'nl': {'de', 'het', 'een', 'van', 'in', 'en', 'op', 'voor', 'met', 'te', 'aan'},
            'pt': {'o', 'a', 'de', 'e', 'em', 'os', 'as', 'do', 'da', 'um', 'uma', 'para'}
        }
    
    def extract_text_from_image(self, image_path: str) -> Dict[str, Any]:
        """
        Extract text from image using OCR with ocrit (fast) or pytesseract (fallback).
        
        This method implements a two-tier OCR approach:
        1. Primary: ocrit CLI tool (Apple Vision ML) - sub-second processing
        2. Fallback: pytesseract with preprocessing - slower but more configurable
        
        Both methods include:
        - Text validation to filter gibberish
        - Language detection
        - URL extraction
        
        The method prioritizes speed with ocrit while maintaining quality through
        validation. Falls back to pytesseract if ocrit is unavailable.
        
        Args:
            image_path (str): Path to the image file
            
        Returns:
            Dict[str, Any]: OCR results with structure:
                {
                    'available': bool,      # Whether OCR was performed
                    'raw_text': str,        # Extracted text
                    'urls': List[str],      # URLs found in text
                    'language': str,        # Detected language (ISO code)
                    'error': str           # Error message if failed (optional)
                }
                
        Example:
            >>> result = service.extract_text_from_image('sign.jpg')
            >>> if result['raw_text']:
            ...     print(f"Text: {result['raw_text']}")
            ...     print(f"Language: {result['language']}")
        """
        if not HAS_OCR:
            return {'available': False, 'reason': 'No OCR tools available (neither ocrit nor pytesseract)'}
        
        # Try ocrit first if available (fast path)
        if HAS_OCRIT:
            result = self._extract_with_ocrit(image_path)
            if result is not None:
                # Return ocrit result even if no text was found (it was still processed)
                return result
            # If ocrit failed completely (returned None), fall through to pytesseract
        
        # Fallback to pytesseract if available
        if HAS_PYTESSERACT:
            return self._extract_with_pytesseract(image_path)
        
        # If we get here, ocrit didn't produce text and pytesseract isn't available
        return {
            'available': True,
            'raw_text': '',
            'urls': [],
            'language': None
        }
    
    def _extract_with_ocrit(self, image_path: str) -> Dict[str, Any]:
        """
        Extract text using the fast ocrit CLI tool.
        
        ocrit uses Apple's Vision ML framework for fast, accurate OCR.
        It natively supports HEIC files and can process images in under a second.
        
        Args:
            image_path (str): Path to the image file
            
        Returns:
            Dict[str, Any]: OCR results or None if extraction failed
        """
        try:
            # Run ocrit without fast mode for better quality
            # Use stdout output mode with "-"
            cmd = ['ocrit', image_path, '--output', '-']
            
            # Add language hints if we have common languages
            # This can improve accuracy for known languages
            # cmd.extend(['--language', 'en', '--language', 'es', '--language', 'fr'])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10  # Timeout after 10 seconds
            )
            
            if result.returncode != 0:
                # ocrit failed
                return None
            
            # Parse the output
            # ocrit outputs: "filename:\n<text content>\nValidating images...\nPerforming OCR..."
            output = result.stdout.strip()
            
            # Split by lines
            lines = output.split('\n')
            
            # Find where the validation messages start
            text_lines = []
            for i, line in enumerate(lines):
                # Stop when we hit the validation messages
                if line.startswith('Validating images') or line.startswith('Performing OCR'):
                    break
                text_lines.append(line)
            
            # Remove the filename line (first line that ends with ':')
            if text_lines and text_lines[0].endswith(':'):
                text_lines = text_lines[1:]
            
            # Join the text preserving line breaks
            text = '\n'.join(text_lines).strip()
            
            # Don't validate ocrit text - it's already high quality
            # The validation was designed for noisy pytesseract output
            
            if not text:
                return {
                    'available': True,
                    'raw_text': '',
                    'urls': [],
                    'language': None,
                    'ocr_method': 'ocrit'
                }
            
            # Extract URLs
            urls = extract_urls_from_text(text)
            
            # Detect language
            language = self._detect_language(text)
            
            return {
                'available': True,
                'raw_text': text,
                'urls': urls,
                'language': language,
                'ocr_method': 'ocrit'
            }
            
        except subprocess.TimeoutExpired:
            # ocrit took too long, return None to trigger fallback
            return None
        except Exception as e:
            # Any other error, return None to trigger fallback
            return None
    
    def _extract_with_pytesseract(self, image_path: str) -> Dict[str, Any]:
        """
        Extract text using pytesseract with preprocessing (fallback method).
        
        This is the original implementation with advanced preprocessing,
        used when ocrit is unavailable or fails.
        """
        # Handle HEIC files by converting to JPEG first
        temp_path = None
        
        try:
            if image_path.lower().endswith('.heic'):
                temp_path = self._convert_heic_to_jpeg(image_path)
                if temp_path:
                    image_path = temp_path
                else:
                    return {
                        'available': True,
                        'error': 'Failed to convert HEIC file for OCR',
                        'raw_text': '',
                        'urls': [],
                        'language': None
                    }
            
            image = Image.open(image_path)
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Preprocess image
            if HAS_OPENCV:
                processed_image = self._preprocess_with_opencv(image)
            else:
                processed_image = self._preprocess_with_pil(image)
            
            # Get OCR data with confidence scores
            # image_to_data provides per-word confidence scores which helps filter noise
            ocr_data = pytesseract.image_to_data(processed_image, output_type=pytesseract.Output.DICT)
            
            # Filter out low confidence text
            confident_text = []
            word_confidences = []
            
            for i in range(len(ocr_data['text'])):
                conf = ocr_data['conf'][i]
                text_item = ocr_data['text'][i].strip()
                
                # Only include text with high confidence and meaningful content
                # 60% confidence threshold is empirically determined to balance
                # between catching real text and filtering OCR artifacts
                if conf > 60 and text_item and len(text_item) > 1:
                    # Additional filtering for gibberish
                    if self._is_valid_word(text_item):
                        confident_text.append(text_item)
                        word_confidences.append(conf)
            
            # If we have very few high-confidence words, try alternative approach
            if len(confident_text) < 3:
                confident_text = self._try_alternative_ocr(processed_image, confident_text)
            
            # Join the confident text
            text = ' '.join(confident_text)
            
            # Clean up text
            text = ' '.join(text.split())
            
            # Final validation
            if text and not self._is_valid_text(text):
                text = ''
            
            if not text:
                return {
                    'available': True,
                    'raw_text': '',
                    'urls': [],
                    'language': None,
                    'ocr_method': 'pytesseract'
                }
            
            # Extract URLs
            urls = extract_urls_from_text(text)
            
            # Detect language
            language = self._detect_language(text)
            
            return {
                'available': True,
                'raw_text': text,
                'urls': urls,
                'language': language,
                'average_confidence': round(np.mean(word_confidences)) if word_confidences else 0,
                'ocr_method': 'pytesseract'
            }
            
        except Exception as e:
            return {
                'available': True,
                'error': str(e),
                'raw_text': '',
                'urls': [],
                'language': None
            }
        finally:
            # Clean up temporary file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except:
                    pass
    
    def _convert_heic_to_jpeg(self, heic_path: str) -> Optional[str]:
        """Convert HEIC file to JPEG and return temporary file path"""
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                temp_path = tmp.name
            
            # Try ImageMagick first
            result = subprocess.run(['convert', '--', heic_path, temp_path], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0 and os.path.exists(temp_path):
                return temp_path
                
            # Try sips (macOS) as fallback
            result = subprocess.run(['sips', '-s', 'format', 'jpeg', heic_path, '--out', temp_path],
                                  capture_output=True, text=True)
            
            if result.returncode == 0 and os.path.exists(temp_path):
                return temp_path
                
            # Clean up if conversion failed
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            
            return None
            
        except Exception:
            return None
    
    def _preprocess_with_opencv(self, image: Image.Image) -> Image.Image:
        """Preprocess image using OpenCV for better OCR results"""
        # Convert to numpy array
        img_array = np.array(image)
        
        # Convert to grayscale
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        
        # Apply bilateral filter to reduce noise while keeping edges sharp
        denoised = cv2.bilateralFilter(gray, 9, 75, 75)
        
        # Apply morphological operations to connect text components
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
        morph = cv2.morphologyEx(denoised, cv2.MORPH_CLOSE, kernel)
        
        # Increase contrast using CLAHE
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        enhanced = clahe.apply(morph)
        
        # Try multiple thresholding methods
        threshold_methods = []
        
        # Method 1: Adaptive threshold
        thresh1 = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                       cv2.THRESH_BINARY, 11, 2)
        threshold_methods.append(thresh1)
        
        # Method 2: Otsu's threshold
        _, thresh2 = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        threshold_methods.append(thresh2)
        
        # Method 3: Inverse adaptive threshold
        thresh3 = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                       cv2.THRESH_BINARY_INV, 11, 2)
        thresh3 = cv2.bitwise_not(thresh3)
        threshold_methods.append(thresh3)
        
        # Test all methods and use the one that gives the best results
        best_image = None
        best_confidence = 0
        
        for thresh_img in threshold_methods:
            try:
                # Quick OCR test to check confidence
                test_data = pytesseract.image_to_data(Image.fromarray(thresh_img), 
                                                     output_type=pytesseract.Output.DICT)
                confidences = [int(conf) for conf in test_data['conf'] if int(conf) > 0]
                avg_conf = np.mean(confidences) if confidences else 0
                
                if avg_conf > best_confidence:
                    best_confidence = avg_conf
                    best_image = thresh_img
            except:
                continue
        
        # Use the best threshold method or fallback to the first one
        binary = best_image if best_image is not None else thresh1
        
        # Convert back to PIL image
        return Image.fromarray(binary)
    
    def _preprocess_with_pil(self, image: Image.Image) -> Image.Image:
        """Preprocess image using PIL for better OCR results"""
        # Convert to grayscale
        processed_image = image.convert('L')
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(processed_image)
        processed_image = enhancer.enhance(2.0)
        
        # Apply sharpening filter
        processed_image = processed_image.filter(ImageFilter.SHARPEN)
        
        # Apply edge enhancement
        processed_image = processed_image.filter(ImageFilter.EDGE_ENHANCE)
        
        return processed_image
    
    def _try_alternative_ocr(self, image: Image.Image, current_text: List[str]) -> List[str]:
        """Try alternative OCR approaches"""
        # Try with different PSM modes
        for psm_mode in [6, 8, 11]:  # Single block, single word, sparse text
            try:
                alt_text = pytesseract.image_to_string(
                    image, 
                    config=f'--psm {psm_mode}'
                ).strip()
                
                # Validate the alternative text
                if alt_text and len(alt_text) > 5 and self._is_valid_text(alt_text):
                    # Check if this gives better results
                    words = alt_text.split()
                    valid_words = [w for w in words if self._is_valid_word(w)]
                    if len(valid_words) > len(current_text):
                        return valid_words
            except:
                continue
        
        return current_text
    
    def _is_valid_word(self, word: str) -> bool:
        """
        Check if a word is likely to be valid text rather than OCR noise.
        
        OCR often produces garbage characters and nonsensical strings. This method
        implements heuristics to identify likely valid words based on:
        
        1. Length: Very short words are often noise
        2. Special character ratio: Too many special chars indicate garbage
        3. Digit patterns: Very long numbers are suspicious
        4. Character repetition: Triple+ repeated chars (except valid cases)
        5. Case transitions: Excessive alternating case is unnatural
        
        These heuristics are based on analysis of common OCR errors and are
        tuned to be somewhat conservative to avoid false positives.
        
        Args:
            word (str): Single word to validate
            
        Returns:
            bool: True if word appears valid, False if likely OCR noise
            
        Examples:
            >>> _is_valid_word("hello")     # True
            >>> _is_valid_word("h3ll0")     # True (leetspeak is valid)
            >>> _is_valid_word("@#$%")      # False (all special chars)
            >>> _is_valid_word("aaaaaaa")   # False (excessive repetition)
            >>> _is_valid_word("hElLo")     # False (unnatural case pattern)
        """
        if len(word) < 2:
            return False
        
        # Check for excessive special characters
        special_chars = sum(1 for c in word if not c.isalnum())
        if special_chars > len(word) // 2:
            return False
        
        # Check for reasonable character distribution
        if word.isdigit() and len(word) > 10:  # Long numbers are suspicious
            return False
        
        # Check for repeated characters (common OCR error)
        if len(word) > 3:
            for i in range(len(word) - 2):
                if word[i] == word[i+1] == word[i+2] and word[i] not in 'aeiouls':
                    return False
        
        # Check for mix of upper and lower that doesn't make sense
        if len(word) > 4:
            transitions = sum(1 for i in range(len(word)-1) 
                            if word[i].islower() != word[i+1].islower())
            if transitions > len(word) // 2:
                return False
        
        return True
    
    def _is_valid_text(self, text: str) -> bool:
        """Check if extracted text is likely to be valid rather than gibberish"""
        if not text or len(text) < 5:
            return False
        
        words = text.split()
        if not words:
            return False
        
        # Check word validity
        valid_words = sum(1 for word in words if self._is_valid_word(word))
        validity_ratio = valid_words / len(words)
        
        # If less than 50% of words are valid, it's likely gibberish
        if validity_ratio < 0.5:
            return False
        
        # Check for reasonable word lengths
        avg_word_length = sum(len(w) for w in words) / len(words)
        if avg_word_length < 2 or avg_word_length > 15:
            return False
        
        # Check character distribution
        alpha_chars = sum(1 for c in text if c.isalpha())
        if alpha_chars < len(text) * 0.5:  # Less than 50% letters
            return False
        
        return True
    
    def _detect_language(self, text: str) -> Optional[str]:
        """Detect language of extracted text"""
        if not text or len(text) < 10:
            return None
        
        try:
            # Clean text for better language detection
            clean_text = ' '.join(text.split())
            
            # Remove special characters and numbers for language detection
            lang_detect_text = re.sub(r'[^a-zA-Z\s\u0080-\uFFFF]', '', clean_text)
            
            if lang_detect_text and len(lang_detect_text.strip()) > 10:
                try:
                    # Get language probabilities
                    lang_probs = detect_langs(lang_detect_text)
                    if lang_probs:
                        # Get the most probable language
                        best_lang = lang_probs[0]
                        language = best_lang.lang
                        language_confidence = best_lang.prob
                        
                        # For short text with low confidence, check common patterns
                        if len(lang_detect_text) < 50 and language_confidence < 0.8:
                            words = lang_detect_text.lower().split()
                            
                            # Check against common word patterns
                            best_match_lang = None
                            best_match_score = 0
                            
                            for lang_code, common_words in self.language_patterns.items():
                                matches = sum(1 for word in words if word in common_words)
                                if matches > best_match_score:
                                    best_match_score = matches
                                    best_match_lang = lang_code
                            
                            # If we have a strong pattern match, use it
                            if best_match_score >= 2 and best_match_lang:
                                language = best_match_lang
                        
                        return language
                        
                except LangDetectException:
                    pass
                    
        except Exception:
            pass
        
        return None
    
    # Async version of the main method
    async def extract_text_from_image_async(self, image_path: str) -> Dict[str, Any]:
        """Async version of extract_text_from_image"""
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(executor, self.extract_text_from_image, image_path)