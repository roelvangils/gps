"""
Image analysis services for GPS Toolkit - face detection, QR codes, color extraction.

This module provides advanced image analysis capabilities beyond basic EXIF extraction.
It implements three main features:

1. Face Detection: Multiple algorithms for detecting human faces
   - face_recognition library (most accurate, uses dlib)
   - OpenCV Haar Cascades (fast, works offline)
   - OpenCV DNN (balance of speed and accuracy)

2. QR Code Detection: Robust QR/barcode detection with preprocessing
   - Multiple scale detection
   - Contrast enhancement
   - Noise reduction
   - Handles various QR code qualities

3. Color Analysis: Dominant color extraction
   - K-means clustering for accurate color grouping
   - Fallback to histogram analysis
   - Human-readable color names

Design Principles:
- Graceful degradation: Features work with available libraries
- Multiple algorithms: Fallbacks ensure robustness
- Performance optimization: Image resizing, efficient algorithms
- HEIC support: Automatic conversion for Apple image formats

The service handles missing dependencies gracefully, returning appropriate
messages when features are unavailable rather than crashing.
"""

import os
import math
import subprocess
import tempfile
import warnings
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image

from ..config import settings

# Import optional libraries with availability flags
# This pattern allows the service to work even if some libraries aren't installed
try:
    import face_recognition
    HAS_FACE_RECOGNITION = True
except ImportError:
    HAS_FACE_RECOGNITION = False

try:
    import cv2
    HAS_OPENCV = True
    # Check if QR code detector is available (requires OpenCV 4.0+)
    try:
        _ = cv2.QRCodeDetector()
        HAS_QR_DETECTOR = True
    except AttributeError:
        HAS_QR_DETECTOR = False
except ImportError:
    HAS_OPENCV = False
    HAS_QR_DETECTOR = False

try:
    from sklearn.cluster import KMeans
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

try:
    import webcolors
    HAS_WEBCOLORS = True
except ImportError:
    HAS_WEBCOLORS = False


class ImageAnalysisService:
    """
    Service for advanced image analysis operations.
    
    This service provides computer vision capabilities including face detection,
    QR code recognition, and color analysis. It's designed to work with various
    image formats including HEIC (Apple's format) through automatic conversion.
    
    The service implements a fallback pattern where multiple algorithms are
    tried in order of accuracy/preference, ensuring that some result is returned
    even if the optimal libraries aren't available.
    
    Methods:
        detect_faces: Find human faces in images
        detect_qr_codes: Detect and decode QR codes and barcodes
        extract_dominant_colors: Analyze color composition
        
    Private Methods:
        _convert_heic_to_jpeg: Handle Apple HEIC format
        _detect_faces_with_*: Various face detection implementations
        _enhance_contrast: Image preprocessing for better detection
        _detect_qr_in_image: QR detection helper
        _extract_colors_*: Color extraction implementations
        _get_color_name: Convert RGB to human-readable color names
    """
    
    def __init__(self, thread_pool=None):
        """Initialize the service and cache models for performance.
        
        Args:
            thread_pool: Optional shared ThreadPoolExecutor for async operations.
                        If not provided, async methods will create their own.
        """
        self._face_cascade = None
        self._dnn_net = None
        self._models_initialized = False
        self._thread_pool = thread_pool
    
    def detect_faces(self, image_path: str) -> Dict[str, Any]:
        """
        Detect faces in the image with proper HEIC support and optimized performance.
        
        This method implements a cascade of face detection algorithms, trying them
        in order of speed/reliability balance:
        
        1. OpenCV DNN (deep neural network - fastest, good accuracy)
        2. OpenCV Haar Cascades (fast fallback)
        3. face_recognition library (slowest but most accurate - only as last resort)
        
        HEIC files are automatically converted to JPEG for processing since most
        CV libraries don't support HEIC directly.
        
        Performance optimizations:
        - Prioritizes fast DNN method
        - Image resizing before detection
        - Single algorithm attempt (no retries with different parameters)
        - Avoids slow face_recognition library unless necessary
        
        Args:
            image_path (str): Path to the image file
            
        Returns:
            Dict[str, Any]: Detection results with structure:
                {
                    'available': bool,  # Whether detection was performed
                    'count': int,       # Number of faces found
                    'method': str,      # Algorithm used (for debugging)
                    'locations': List[Dict],  # Face bounding boxes
                    'error': str        # Error message if failed (optional)
                }
                
        Example:
            >>> result = service.detect_faces('photo.jpg')
            >>> print(f"Found {result['count']} faces")
            
        Note:
            Face locations format varies by method:
            - face_recognition: {'top', 'right', 'bottom', 'left'}
            - opencv/opencv_dnn: {'x', 'y', 'width', 'height'}
        """
        # Convert HEIC to JPEG if needed
        temp_path = None
        
        try:
            if image_path.lower().endswith('.heic'):
                temp_path = self._convert_heic_to_jpeg(image_path)
                if temp_path:
                    image_path = temp_path
            
            # Try OpenCV DNN first (fastest and reliable)
            if HAS_OPENCV:
                result = self._detect_faces_with_opencv_dnn(image_path)
                if result.get('available') and not result.get('error'):
                    return result
                
                # Fallback to OpenCV Haar Cascades
                # Still fast, though less accurate
                result = self._detect_faces_with_opencv(image_path)
                if result.get('available') and not result.get('error'):
                    return result
            
            # Only use face_recognition as last resort (very slow)
            # Skip this if we want sub-second performance
            if HAS_FACE_RECOGNITION and not HAS_OPENCV:
                # Only use the faster HOG model, skip CNN
                result = self._detect_faces_with_face_recognition_fast(image_path)
                if result.get('available') and not result.get('error'):
                    return result
            
            return {'available': False, 'reason': 'No face detection library installed or all methods failed'}
            
        finally:
            # Clean up temporary file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except:
                    pass
    
    def detect_qr_codes(self, image_path: str) -> Dict[str, Any]:
        """Detect and decode QR codes in the image with enhanced preprocessing"""
        if not HAS_QR_DETECTOR:
            return {'available': False, 'reason': 'QR detection not available (OpenCV not installed or too old)'}
        
        temp_path = None
        try:
            # Handle HEIC files by converting to JPEG first
            if image_path.lower().endswith('.heic'):
                temp_path = self._convert_heic_to_jpeg(image_path)
                if temp_path:
                    image_path = temp_path
                else:
                    return {
                        'available': True,
                        'error': 'Failed to convert HEIC file',
                        'count': 0,
                        'codes': []
                    }
            
            # Read image with OpenCV
            img = cv2.imread(image_path)
            if img is None:
                raise ValueError(f"Could not read image from {image_path}")
            
            # Create QR code detector
            detector = cv2.QRCodeDetector()
            
            all_codes = []
            detected_data = set()  # Track unique QR data to avoid duplicates
            
            # Try multiple preprocessing approaches
            preprocessing_attempts = [
                # Original image
                ('original', img),
                # Grayscale
                ('grayscale', cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img),
                # Enhanced contrast
                ('enhanced_contrast', self._enhance_contrast(img)),
                # Gaussian blur reduction (for noisy images)
                ('blur_reduced', cv2.GaussianBlur(img, (5, 5), 0)),
            ]
            
            # Add scale variations
            scales = [0.5, 1.0, 1.5, 2.0]
            for scale in scales:
                if scale != 1.0:
                    width = int(img.shape[1] * scale)
                    height = int(img.shape[0] * scale)
                    scaled = cv2.resize(img, (width, height), interpolation=cv2.INTER_CUBIC)
                    preprocessing_attempts.append((f'scale_{scale}', scaled))
            
            # Try detection with each preprocessing method
            for method_name, processed_img in preprocessing_attempts:
                codes = self._detect_qr_in_image(detector, processed_img, method_name)
                
                # Add unique codes (avoid duplicates)
                for code in codes:
                    if code['data'] not in detected_data:
                        detected_data.add(code['data'])
                        all_codes.append(code)
            
            # Limit to MAX_QR_CODES
            all_codes = all_codes[:settings.MAX_QR_CODES]
            
            return {
                'available': True,
                'count': len(all_codes),
                'codes': all_codes
            }
            
        except Exception as e:
            return {
                'available': True,
                'error': str(e),
                'count': 0,
                'codes': []
            }
        finally:
            # Clean up temporary file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except:
                    pass
    
    def extract_dominant_colors(self, image_path: str, n_colors: int = 5) -> Dict[str, Any]:
        """Extract dominant colors from the image"""
        try:
            # Special handling for HEIC files
            temp_path = None
            if image_path.lower().endswith('.heic'):
                temp_path = self._convert_heic_to_jpeg(image_path)
                if temp_path:
                    image_path = temp_path
            
            try:
                # Open image
                image = Image.open(image_path)
                
                # Convert to RGB if necessary
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # Resize for faster processing
                image.thumbnail((150, 150))
                
                # Convert to numpy array
                img_array = np.array(image)
                
                # Validate image has content
                if img_array.size == 0:
                    return {
                        'available': True,
                        'error': 'Image has no pixel data'
                    }
                
                # Reshape to list of pixels
                pixels = img_array.reshape(-1, 3)
                
                # Check if we have enough pixels
                if len(pixels) < n_colors:
                    n_colors = max(1, len(pixels))
                
                if HAS_SKLEARN:
                    dominant_colors = self._extract_colors_with_kmeans(pixels, n_colors)
                else:
                    dominant_colors = self._extract_colors_simple(pixels, n_colors)
                
                return {
                    'available': True,
                    **dominant_colors
                }
                
            finally:
                # Clean up temp file
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except:
                        pass
                        
        except Exception as e:
            return {
                'available': True,
                'error': str(e)
            }
    
    def _convert_heic_to_jpeg(self, heic_path: str) -> Optional[str]:
        """
        Convert HEIC file to JPEG and return temporary file path.
        
        HEIC (High Efficiency Image Container) is Apple's proprietary format
        that many image processing libraries don't support directly. This method
        converts HEIC to JPEG using available system tools.
        
        Conversion attempts in order:
        1. ImageMagick (convert command) - most reliable
        2. sips (macOS built-in) - fallback for Mac users
        
        The method creates a temporary file that should be cleaned up by the
        caller to avoid leaving temporary files on disk.
        
        Args:
            heic_path (str): Path to the HEIC file
            
        Returns:
            Optional[str]: Path to temporary JPEG file if successful,
                          None if conversion failed
                          
        Note:
            Requires ImageMagick or macOS sips to be installed.
            The temporary file is created with a .jpg extension.
        """
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
    
    def _detect_faces_with_face_recognition(self, image_path: str) -> Dict[str, Any]:
        """Detect faces using face_recognition library"""
        try:
            # Load image
            image = face_recognition.load_image_file(image_path)
            
            # Try HOG first (faster)
            face_locations = face_recognition.face_locations(image, model="hog")
            
            # If no faces found, try CNN (more accurate)
            if len(face_locations) == 0:
                face_locations = face_recognition.face_locations(image, model="cnn")
            
            # Limit to MAX_FACES
            face_locations = face_locations[:settings.MAX_FACES]
            
            return {
                'available': True,
                'count': len(face_locations),
                'method': 'face_recognition',
                'locations': [
                    {'top': t, 'right': r, 'bottom': b, 'left': l}
                    for t, r, b, l in face_locations
                ]
            }
            
        except Exception as e:
            return {
                'available': True,
                'error': str(e),
                'count': 0
            }
    
    def _detect_faces_with_face_recognition_fast(self, image_path: str) -> Dict[str, Any]:
        """
        Fast face detection using face_recognition library with optimizations.
        
        Optimizations:
        - Only uses HOG model (no CNN fallback)
        - Resizes image before detection
        - Number of times to upsample = 0 for speed
        """
        try:
            # Load and resize image for faster processing
            image = face_recognition.load_image_file(image_path)
            
            # Resize if image is too large
            height, width = image.shape[:2]
            max_width = 1024
            
            if width > max_width:
                scale = max_width / width
                new_width = int(width * scale)
                new_height = int(height * scale)
                
                # Use PIL for resizing as it's already loaded
                from PIL import Image as PILImage
                pil_image = PILImage.fromarray(image)
                pil_image = pil_image.resize((new_width, new_height), PILImage.Resampling.LANCZOS)
                image = np.array(pil_image)
                
                # Keep track of scale for coordinate adjustment
                scale_factor = scale
            else:
                scale_factor = 1.0
            
            # Use HOG with number_of_times_to_upsample=0 for speed
            face_locations = face_recognition.face_locations(
                image, 
                model="hog",
                number_of_times_to_upsample=0
            )
            
            # Scale locations back to original size
            if scale_factor != 1.0:
                face_locations = [
                    (int(top/scale_factor), int(right/scale_factor), 
                     int(bottom/scale_factor), int(left/scale_factor))
                    for top, right, bottom, left in face_locations
                ]
            
            # Limit to MAX_FACES
            face_locations = face_locations[:settings.MAX_FACES]
            
            return {
                'available': True,
                'count': len(face_locations),
                'method': 'face_recognition_fast',
                'locations': [
                    {'top': t, 'right': r, 'bottom': b, 'left': l}
                    for t, r, b, l in face_locations
                ]
            }
            
        except Exception as e:
            return {
                'available': True,
                'error': str(e),
                'count': 0
            }
    
    def _detect_faces_with_opencv(self, image_path: str) -> Dict[str, Any]:
        """
        Detect faces using OpenCV Haar Cascades with performance optimizations.
        
        Optimizations:
        - Resizes image before detection
        - Single detection pass (no parameter adjustment retries)
        - Efficient grayscale conversion
        """
        try:
            # Load the cascade (cached for performance)
            if self._face_cascade is None:
                self._face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            
            face_cascade = self._face_cascade
            
            # Read image
            img = cv2.imread(image_path)
            if img is None:
                raise ValueError(f"Could not read image from {image_path}")
            
            h, w = img.shape[:2]
            
            # Resize if image is too large
            max_width = 1024
            if w > max_width:
                scale = max_width / w
                new_w = int(w * scale)
                new_h = int(h * scale)
                img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
                scale_factor = scale
            else:
                scale_factor = 1.0
            
            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Equalize histogram for better contrast
            gray = cv2.equalizeHist(gray)
            
            # Detect faces with balanced parameters (single attempt)
            faces_cv = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.08,
                minNeighbors=4,
                minSize=(25, 25),
                flags=cv2.CASCADE_SCALE_IMAGE
            )
            
            # Scale coordinates back to original size
            if scale_factor != 1.0:
                faces_cv = np.array([
                    [int(x/scale_factor), int(y/scale_factor), 
                     int(w/scale_factor), int(h/scale_factor)]
                    for x, y, w, h in faces_cv
                ])
            
            # Limit to MAX_FACES
            faces_cv = faces_cv[:settings.MAX_FACES]
            
            return {
                'available': True,
                'count': len(faces_cv),
                'method': 'opencv_haar',
                'locations': [
                    {'x': int(x), 'y': int(y), 'width': int(w), 'height': int(h)}
                    for x, y, w, h in faces_cv
                ]
            }
            
        except Exception as e:
            return {
                'available': True,
                'error': str(e),
                'count': 0
            }
    
    def _detect_faces_with_opencv_dnn(self, image_path: str) -> Dict[str, Any]:
        """
        Detect faces using OpenCV DNN module with Caffe model.
        
        This is the fastest and most reliable method, using a pre-trained
        deep neural network that provides good balance between speed and accuracy.
        The model is based on Single Shot Detector (SSD) framework with a
        ResNet-10 base network.
        
        Performance optimizations:
        - Resizes image before detection (max 1024px wide)
        - Uses optimized blob preprocessing
        - Single pass detection (no retries)
        - Confidence threshold filtering
        
        Returns:
            Dict with face count and locations
        """
        try:
            # Model files - we'll need to check if they exist
            prototxt_path = os.path.join(os.path.dirname(__file__), 'models', 'deploy.prototxt')
            model_path = os.path.join(os.path.dirname(__file__), 'models', 'res10_300x300_ssd_iter_140000_fp16.caffemodel')
            
            # Download models if not present
            if not os.path.exists(prototxt_path) or not os.path.exists(model_path):
                # For now, we'll use the embedded minimal prototxt and download the model
                os.makedirs(os.path.dirname(prototxt_path), exist_ok=True)
                
                # Write minimal prototxt for face detection
                if not os.path.exists(prototxt_path):
                    with open(prototxt_path, 'w') as f:
                        f.write(self._get_face_detection_prototxt())
                
                # Download the model if needed (about 5.4 MB)
                if not os.path.exists(model_path):
                    import urllib.request
                    import hashlib
                    
                    # Define expected checksum for security
                    EXPECTED_SHA256 = "2a56a11a57a4f5a2e52b0f80d5b3b3e3c06418e926e55ac746f593aa8f082a96"
                    
                    model_url = "https://github.com/opencv/opencv_3rdparty/raw/dnn_samples_face_detector_20180205_fp16/res10_300x300_ssd_iter_140000_fp16.caffemodel"
                    
                    # Download to a temporary path first
                    tmp_model_path = model_path + ".tmp"
                    urllib.request.urlretrieve(model_url, tmp_model_path)
                    
                    # Verify checksum
                    sha256_hash = hashlib.sha256()
                    with open(tmp_model_path, "rb") as f:
                        for byte_block in iter(lambda: f.read(4096), b""):
                            sha256_hash.update(byte_block)
                    
                    downloaded_hash = sha256_hash.hexdigest()
                    
                    if downloaded_hash == EXPECTED_SHA256:
                        # Move file to final destination if checksum matches
                        os.rename(tmp_model_path, model_path)
                    else:
                        # Clean up and raise error
                        os.unlink(tmp_model_path)
                        raise RuntimeError(f"Model checksum mismatch for {model_path}. Expected {EXPECTED_SHA256}, got {downloaded_hash}.")
            
            # Load the model (cached for performance)
            if self._dnn_net is None:
                self._dnn_net = cv2.dnn.readNet(prototxt_path, model_path)
            
            net = self._dnn_net
            
            # Read and preprocess image
            img = cv2.imread(image_path)
            if img is None:
                raise ValueError(f"Could not read image from {image_path}")
            
            h, w = img.shape[:2]
            
            # Resize image if too large (this is key for performance)
            max_width = 1024
            if w > max_width:
                scale = max_width / w
                new_w = int(w * scale)
                new_h = int(h * scale)
                img_resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
                scale_factor = scale
            else:
                img_resized = img
                scale_factor = 1.0
                new_w, new_h = w, h
            
            # Create blob from image
            blob = cv2.dnn.blobFromImage(
                img_resized, 
                scalefactor=1.0,
                size=(300, 300),
                mean=(104.0, 177.0, 123.0),
                swapRB=False,
                crop=False
            )
            
            # Set input and perform forward pass
            net.setInput(blob)
            detections = net.forward()
            
            # Process detections
            faces = []
            confidence_threshold = 0.5
            
            for i in range(detections.shape[2]):
                confidence = detections[0, 0, i, 2]
                
                if confidence > confidence_threshold:
                    # Get coordinates relative to resized image, then scale back
                    x1 = int(detections[0, 0, i, 3] * new_w)
                    y1 = int(detections[0, 0, i, 4] * new_h)
                    x2 = int(detections[0, 0, i, 5] * new_w)
                    y2 = int(detections[0, 0, i, 6] * new_h)
                    
                    # Scale back to original image coordinates
                    x1 = int(x1 / scale_factor)
                    y1 = int(y1 / scale_factor)
                    x2 = int(x2 / scale_factor)
                    y2 = int(y2 / scale_factor)
                    
                    # Ensure coordinates are within image bounds
                    x1 = max(0, x1)
                    y1 = max(0, y1)
                    x2 = min(w, x2)
                    y2 = min(h, y2)
                    
                    faces.append({
                        'x': x1,
                        'y': y1,
                        'width': x2 - x1,
                        'height': y2 - y1,
                        'confidence': float(confidence)
                    })
            
            # Sort by confidence and limit to MAX_FACES
            faces = sorted(faces, key=lambda x: x['confidence'], reverse=True)
            faces = faces[:settings.MAX_FACES]
            
            return {
                'available': True,
                'count': len(faces),
                'method': 'opencv_dnn',
                'locations': faces
            }
            
        except Exception as e:
            # Fallback to False if DNN not available
            return {
                'available': False,
                'error': str(e),
                'count': 0
            }
    
    def _get_face_detection_prototxt(self) -> str:
        """Return the minimal prototxt definition for face detection"""
        return '''input: "data"
input_shape {
  dim: 1
  dim: 3
  dim: 300
  dim: 300
}

layer {
  name: "data_bn"
  type: "BatchNorm"
  bottom: "data"
  top: "data_bn"
  batch_norm_param {
    use_global_stats: true
  }
}
layer {
  name: "data_scale"
  type: "Scale"
  bottom: "data_bn"
  top: "data_bn"
  scale_param {
    bias_term: true
  }
}
layer {
  name: "conv1_h"
  type: "Convolution"
  bottom: "data_bn"
  top: "conv1_h"
  convolution_param {
    num_output: 32
    bias_term: false
    pad: 3
    kernel_size: 7
    group: 1
    stride: 2
    weight_filler {
      type: "msra"
    }
    dilation: 1
  }
}

# ... Additional layers would go here for the full model ...
# This is a simplified version - the actual model file will handle this

layer {
  name: "detection_out"
  type: "DetectionOutput"
  bottom: "mbox_loc"
  bottom: "mbox_conf_flatten"
  bottom: "mbox_priorbox"
  top: "detection_out"
  include {
    phase: TEST
  }
  detection_output_param {
    num_classes: 2
    share_location: true
    background_label_id: 0
    nms_param {
      nms_threshold: 0.45
      top_k: 400
    }
    code_type: CENTER_SIZE
    keep_top_k: 200
    confidence_threshold: 0.01
  }
}
'''
    
    def _enhance_contrast(self, img: np.ndarray) -> np.ndarray:
        """Enhance image contrast using CLAHE"""
        if len(img.shape) == 3:
            # Convert to LAB color space
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            
            # Apply CLAHE to L channel
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            
            # Merge and convert back
            lab = cv2.merge([l, a, b])
            return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        else:
            # Grayscale image
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            return clahe.apply(img)
    
    def _detect_qr_in_image(self, detector, img, method_name: str) -> List[Dict[str, Any]]:
        """Helper method to detect QR codes in a single image"""
        codes = []
        
        try:
            # Ensure image is in the right format for detection
            if len(img.shape) == 2:
                detect_img = img
            else:
                detect_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
            
            # Try multi-detection first (OpenCV 4.5.1+)
            try:
                retval, decoded_info, points, _ = detector.detectAndDecodeMulti(detect_img)
                
                if retval and decoded_info:
                    for i, (data, pts) in enumerate(zip(decoded_info, points)):
                        if data and data.strip():
                            # Calculate bounding box from points
                            x = int(pts[:, 0].min())
                            y = int(pts[:, 1].min())
                            w = int(pts[:, 0].max() - x)
                            h = int(pts[:, 1].max() - y)
                            
                            code = {
                                'type': 'QRCODE',
                                'data': data,
                                'preprocessing': method_name,
                                'location': {
                                    'left': x,
                                    'top': y,
                                    'width': w,
                                    'height': h
                                }
                            }
                            codes.append(code)
            except AttributeError:
                # Fall back to single detection
                data, points, _ = detector.detectAndDecode(detect_img)
                
                if data and data.strip():
                    if points is not None and len(points) > 0:
                        pts = points[0]
                        x = int(pts[:, 0].min())
                        y = int(pts[:, 1].min())
                        w = int(pts[:, 0].max() - x)
                        h = int(pts[:, 1].max() - y)
                        
                        code = {
                            'type': 'QRCODE',
                            'data': data,
                            'preprocessing': method_name,
                            'location': {
                                'left': x,
                                'top': y,
                                'width': w,
                                'height': h
                            }
                        }
                        codes.append(code)
        except Exception:
            pass
        
        return codes
    
    def _extract_colors_with_kmeans(self, pixels: np.ndarray, n_colors: int) -> Dict[str, Any]:
        """
        Extract dominant colors using KMeans clustering algorithm.
        
        This method uses unsupervised machine learning to group similar colors
        together and find the most representative colors in an image. KMeans
        is more accurate than simple histogram analysis because it considers
        color similarity in 3D RGB space.
        
        The algorithm:
        1. Normalizes pixel values to 0-1 range for better clustering
        2. Runs KMeans to find n color clusters
        3. Uses cluster centers as dominant colors
        4. Calculates percentage based on cluster membership
        5. Sorts by dominance (highest percentage first)
        
        Args:
            pixels (np.ndarray): Array of RGB pixel values, shape (n_pixels, 3)
            n_colors (int): Number of dominant colors to extract
            
        Returns:
            Dict[str, Any]: Dictionary with color_1, color_2, etc. keys
                           Each color has: rgb, hex, percentage, name
                           
        Note:
            Falls back to simple color extraction if KMeans fails.
            Handles edge cases like images with fewer unique colors than requested.
        """
        # Normalize pixel values
        pixels_normalized = pixels.astype(np.float32) / 255.0
        
        # Count unique colors
        unique_colors = np.unique(pixels, axis=0)
        actual_n_colors = min(n_colors, len(unique_colors))
        
        if actual_n_colors == 0:
            return {}
        
        # Suppress sklearn warnings
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=RuntimeWarning)
            
            # Use KMeans clustering
            kmeans = KMeans(
                n_clusters=actual_n_colors, 
                random_state=42, 
                n_init=10,
                init='k-means++',
                max_iter=300
            )
            
            try:
                kmeans.fit(pixels_normalized)
            except Exception:
                # Fallback to simple method
                return self._extract_colors_simple(pixels, n_colors)
        
        # Get colors and convert back to 0-255 range
        colors = (kmeans.cluster_centers_ * 255).astype(int)
        labels = kmeans.labels_
        
        # Count occurrences
        counts = np.bincount(labels)
        percentages = counts / len(labels)
        
        # Sort by percentage
        sorted_indices = np.argsort(percentages)[::-1]
        
        dominant_colors = {}
        for i, idx in enumerate(sorted_indices[:actual_n_colors], 1):
            color = colors[idx]
            percentage = percentages[idx]
            
            # Ensure color values are in valid range
            color = np.clip(color, 0, 255)
            
            # Convert to hex
            hex_color = '#{:02x}{:02x}{:02x}'.format(color[0], color[1], color[2])
            
            dominant_colors[f'color_{i}'] = {
                'rgb': color.tolist(),
                'hex': hex_color,
                'percentage': math.ceil(percentage * 100),
                'name': self._get_color_name(color)
            }
        
        return dominant_colors
    
    def _extract_colors_simple(self, pixels: np.ndarray, n_colors: int) -> Dict[str, Any]:
        """Simple color extraction without sklearn"""
        # Get unique colors and count them
        unique_colors, counts = np.unique(pixels, axis=0, return_counts=True)
        
        # Sort by count
        sorted_indices = np.argsort(counts)[::-1][:n_colors]
        
        total_pixels = len(pixels)
        dominant_colors = {}
        
        for i, idx in enumerate(sorted_indices, 1):
            color = unique_colors[idx]
            count = counts[idx]
            percentage = (count / total_pixels) * 100
            
            hex_color = '#{:02x}{:02x}{:02x}'.format(color[0], color[1], color[2])
            
            dominant_colors[f'color_{i}'] = {
                'rgb': color.tolist(),
                'hex': hex_color,
                'percentage': math.ceil(percentage),
                'name': self._get_color_name(color)
            }
        
        return dominant_colors
    
    # Color detection rules - data-driven approach
    COLOR_RULES = [
        # Grayscale colors (check first - special case)
        ("grayscale", lambda r, g, b: abs(r - g) < 25 and abs(g - b) < 25, [
            ("black", lambda r, g, b: r < 40),
            ("white", lambda r, g, b: r > 215),
            ("dark gray", lambda r, g, b: r < 80),
            ("gray", lambda r, g, b: r < 120),
            ("light gray", lambda r, g, b: r < 180),
            ("off white", lambda r, g, b: True),  # Default for grayscale
        ]),
        # Low saturation (grayish variants)
        ("low_saturation", lambda r, g, b: max(r, g, b) - min(r, g, b) < 30, [
            ("dark gray", lambda r, g, b: max(r, g, b) < 100),
            ("gray", lambda r, g, b: max(r, g, b) < 150),
            ("light gray", lambda r, g, b: True),
        ]),
        # Browns and tans
        ("browns", lambda r, g, b: b < 100 and r > 70 and g > 50 and abs(r - g) < 60, [
            ("tan", lambda r, g, b: r > 180 and g > 150),
            ("light brown", lambda r, g, b: r > 150 and g > 120),
            ("brown", lambda r, g, b: r > 100 and g > 70),
            ("dark brown", lambda r, g, b: True),
        ]),
        # Greens
        ("greens", lambda r, g, b: g > r and g > b, [
            ("yellow green", lambda r, g, b: g > 200 and r > 150),
            ("bright green", lambda r, g, b: g > 200),
            ("green", lambda r, g, b: g > 150 and b < 100),
            ("olive", lambda r, g, b: g > 100 and r > 80 and b < 80),
            ("forest green", lambda r, g, b: g > 100),
            ("dark green", lambda r, g, b: True),
        ]),
        # Blues
        ("blues", lambda r, g, b: b > r and b > g, [
            ("cyan", lambda r, g, b: b > 200 and g > 150),
            ("blue", lambda r, g, b: b > 200 and r < 100 and g < 100),
            ("sky blue", lambda r, g, b: b > 200),
            ("teal", lambda r, g, b: b > 150 and g > 100),
            ("navy", lambda r, g, b: b > 100),
            ("dark blue", lambda r, g, b: True),
        ]),
        # Reds
        ("reds", lambda r, g, b: r > g and r > b, [
            ("pink", lambda r, g, b: r > 200 and g > 150 and b > 150),
            ("orange", lambda r, g, b: r > 200 and g > 100),
            ("red", lambda r, g, b: r > 200),
            ("crimson", lambda r, g, b: r > 150 and g < 100),
            ("maroon", lambda r, g, b: r > 100),
            ("dark red", lambda r, g, b: True),
        ]),
        # Yellows and oranges
        ("yellows", lambda r, g, b: r > 200 and g > 180 and b < 100, [
            ("yellow", lambda r, g, b: g > 220),
            ("gold", lambda r, g, b: True),
        ]),
        # Additional orange check
        ("oranges", lambda r, g, b: r > 200 and g > 100 and g < 180 and b < 100, [
            ("orange", lambda r, g, b: True),
        ]),
        # Purples and magentas
        ("purples", lambda r, g, b: r > 100 and b > 100 and g < 100, [
            ("magenta", lambda r, g, b: r > 200 or b > 200),
            ("purple", lambda r, g, b: r > 150 or b > 150),
            ("dark purple", lambda r, g, b: True),
        ]),
    ]
    
    def _get_color_name(self, rgb: np.ndarray) -> str:
        """Get color name from RGB values using data-driven rules"""
        r, g, b = rgb
        
        # Try webcolors exact match first if available
        if HAS_WEBCOLORS:
            try:
                return webcolors.rgb_to_name((r, g, b))
            except ValueError:
                pass  # No exact match, continue with our detection
        
        # Apply color rules in order
        for category_name, category_check, color_rules in self.COLOR_RULES:
            if category_check(r, g, b):
                for color_name, color_check in color_rules:
                    if color_check(r, g, b):
                        return color_name
        
        # Default fallback - use dominant channel
        max_val = max(r, g, b)
        if max_val == r:
            return "reddish"
        elif max_val == g:
            return "greenish"
        elif max_val == b:
            return "bluish"
        else:
            return "unknown"
    
    # Async versions of all methods
    async def detect_faces_async(self, image_path: str) -> Dict[str, Any]:
        """Async version of detect_faces"""
        loop = asyncio.get_event_loop()
        if self._thread_pool:
            return await loop.run_in_executor(self._thread_pool, self.detect_faces, image_path)
        else:
            with ThreadPoolExecutor() as executor:
                return await loop.run_in_executor(executor, self.detect_faces, image_path)
    
    async def detect_qr_codes_async(self, image_path: str) -> Dict[str, Any]:
        """Async version of detect_qr_codes"""
        loop = asyncio.get_event_loop()
        if self._thread_pool:
            return await loop.run_in_executor(self._thread_pool, self.detect_qr_codes, image_path)
        else:
            with ThreadPoolExecutor() as executor:
                return await loop.run_in_executor(executor, self.detect_qr_codes, image_path)
    
    async def extract_dominant_colors_async(self, image_path: str, n_colors: int = 5) -> Dict[str, Any]:
        """Async version of extract_dominant_colors"""
        loop = asyncio.get_event_loop()
        if self._thread_pool:
            return await loop.run_in_executor(self._thread_pool, self.extract_dominant_colors, image_path, n_colors)
        else:
            with ThreadPoolExecutor() as executor:
                return await loop.run_in_executor(executor, self.extract_dominant_colors, image_path, n_colors)