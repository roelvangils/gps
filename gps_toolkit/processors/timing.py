"""Timing context manager for debugging and performance monitoring"""

import sys
import time
from datetime import datetime


class TimingContext:
    """Context manager for timing operations and outputting debug info to stderr"""
    
    def __init__(self, step_name: str, debug: bool = False):
        self.step_name = step_name
        self.debug = debug
        self.start_time = None
        self.start_timestamp = None
    
    def __enter__(self):
        if self.debug:
            self.start_time = time.time()
            self.start_timestamp = datetime.now()
            start_str = self.start_timestamp.strftime("%H:%M:%S.%f")[:-3]  # HH:MM:SS.mmm
            sys.stderr.write(f"[DEBUG] {self.step_name}: Started at {start_str}\n")
            sys.stderr.flush()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.debug:
            end_time = time.time()
            duration = end_time - self.start_time
            start_str = self.start_timestamp.strftime("%H:%M:%S.%f")[:-3]
            sys.stderr.write(f"[DEBUG] {self.step_name}: Started at {start_str}, took {duration:.3f}s\n")
            sys.stderr.flush()