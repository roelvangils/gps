#!/usr/bin/env python3
"""
GPS Toolkit Setup
Enhanced GPS Location Extractor with image analysis capabilities
"""

from setuptools import setup, find_packages
import os

# Read README for long description
def read_readme():
    """Read README file for long description"""
    readme_path = os.path.join(os.path.dirname(__file__), 'README.md')
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            return f.read()
    return "Enhanced GPS Location Extractor with advanced image analysis capabilities"

setup(
    name="gps-toolkit",
    version="2.0.0",
    description="Enhanced GPS Location Extractor with image analysis capabilities",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    author="GPS Toolkit",
    author_email="gps-toolkit@example.com",
    url="https://github.com/user/gps-toolkit",
    packages=find_packages(),
    python_requires=">=3.7",
    
    # Core dependencies (required)
    install_requires=[
        "Pillow>=8.0.0",
        "numpy>=1.19.0",
        "requests>=2.25.0",
        "aiohttp>=3.8.0",
        "aiodns>=3.0.0",
    ],
    
    # Optional dependencies
    extras_require={
        "opencv": ["opencv-contrib-python>=4.5.0"],
        "ocr": ["pytesseract>=0.3.8", "langdetect>=1.0.9"],
        "face": ["face-recognition>=1.3.0"],
        "color": ["scikit-learn>=0.24.0", "webcolors>=1.11.0"],
        "moon": ["ephem>=4.1.0"],
        "web": ["trafilatura>=1.6.0"],
        "all": [
            "opencv-contrib-python>=4.5.0",
            "pytesseract>=0.3.8",
            "langdetect>=1.0.9", 
            "face-recognition>=1.3.0",
            "scikit-learn>=0.24.0",
            "webcolors>=1.11.0",
            "ephem>=4.1.0",
            "trafilatura>=1.6.0"
        ]
    },
    
    # CLI entry points
    entry_points={
        'console_scripts': [
            'gps-toolkit=gps_toolkit.cli:main',
        ],
    },
    
    # Package data
    package_data={
        'gps_toolkit.services': ['models/*'],
    },
    include_package_data=True,
    
    # Classifiers
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Multimedia :: Graphics",
        "Topic :: Scientific/Engineering :: GIS",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    
    # Keywords
    keywords="gps exif location geocoding image-analysis face-detection ocr qr-code weather",
    
    # Project URLs
    project_urls={
        "Documentation": "https://github.com/user/gps-toolkit/docs",
        "Source": "https://github.com/user/gps-toolkit",
        "Tracker": "https://github.com/user/gps-toolkit/issues",
    },
)