"""
Async coordinator for the GPS toolkit to enable concurrent execution of independent operations.

This module provides a centralized way to group and execute independent operations
concurrently, reducing total processing time while maintaining proper error handling
and timing information for debug output.
"""

import asyncio
import time
import sys
from datetime import datetime
from typing import List, Dict, Any, Callable, Optional, Awaitable, Tuple
from concurrent.futures import ThreadPoolExecutor


class AsyncTimingContext:
    """Async-compatible context manager for timing operations"""
    
    def __init__(self, step_name: str, debug: bool = False):
        self.step_name = step_name
        self.debug = debug
        self.start_time = None
        self.start_timestamp = None
    
    async def __aenter__(self):
        if self.debug:
            self.start_time = time.time()
            self.start_timestamp = datetime.now()
            start_str = self.start_timestamp.strftime("%H:%M:%S.%f")[:-3]
            sys.stderr.write(f"[DEBUG] {self.step_name}: Started at {start_str}\n")
            sys.stderr.flush()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.debug:
            end_time = time.time()
            duration = end_time - self.start_time
            start_str = self.start_timestamp.strftime("%H:%M:%S.%f")[:-3]
            sys.stderr.write(f"[DEBUG] {self.step_name}: Started at {start_str}, took {duration:.3f}s\n")
            sys.stderr.flush()


class TaskGroup:
    """Represents a group of independent tasks that can run concurrently"""
    
    def __init__(self, name: str, debug: bool = False, thread_pool=None):
        self.name = name
        self.debug = debug
        self.thread_pool = thread_pool
        self.tasks: List[Tuple[str, Callable, tuple, dict]] = []
    
    def add_task(self, name: str, func: Callable, *args, **kwargs):
        """Add a task to this group"""
        self.tasks.append((name, func, args, kwargs))
    
    async def execute(self) -> Dict[str, Any]:
        """Execute all tasks in this group concurrently"""
        if not self.tasks:
            return {}
        
        async with AsyncTimingContext(f"Task Group: {self.name}", self.debug):
            # Create coroutines for all tasks
            coroutines = []
            task_names = []
            
            for task_name, func, args, kwargs in self.tasks:
                task_names.append(task_name)
                if asyncio.iscoroutinefunction(func):
                    # It's an async function
                    coroutines.append(func(*args, **kwargs))
                else:
                    # It's a sync function, run in thread pool
                    coroutines.append(self._run_in_thread(func, *args, **kwargs))
            
            # Execute all tasks concurrently
            try:
                results = await asyncio.gather(*coroutines, return_exceptions=True)
                
                # Package results with task names
                grouped_results = {}
                for task_name, result in zip(task_names, results):
                    if isinstance(result, Exception):
                        if self.debug:
                            sys.stderr.write(f"[DEBUG] Task {task_name} failed: {result}\n")
                        grouped_results[task_name] = {'error': str(result)}
                    else:
                        grouped_results[task_name] = result
                
                return grouped_results
                
            except Exception as e:
                if self.debug:
                    sys.stderr.write(f"[DEBUG] Task Group {self.name} failed: {e}\n")
                return {'error': str(e)}
    
    async def _run_in_thread(self, func: Callable, *args, **kwargs) -> Any:
        """Run a synchronous function in a thread pool"""
        loop = asyncio.get_event_loop()
        executor = self.thread_pool if self.thread_pool else None
        return await loop.run_in_executor(executor, lambda: func(*args, **kwargs))


class AsyncCoordinator:
    """
    Coordinates async processing for the GPS toolkit.
    
    This class organizes independent operations into groups that can be executed
    concurrently, reducing total processing time while maintaining proper error
    handling and timing information.
    """
    
    def __init__(self, debug: bool = False, thread_pool=None):
        self.debug = debug
        self.thread_pool = thread_pool
        self.groups: List[TaskGroup] = []
    
    def create_group(self, name: str) -> TaskGroup:
        """Create a new task group"""
        group = TaskGroup(name, self.debug, self.thread_pool)
        self.groups.append(group)
        return group
    
    async def execute_all_groups(self) -> Dict[str, Any]:
        """Execute all groups sequentially (groups run in parallel internally)"""
        all_results = {}
        
        for group in self.groups:
            group_results = await group.execute()
            all_results.update(group_results)
        
        return all_results
    
    async def execute_groups_concurrently(self) -> Dict[str, Any]:
        """Execute all groups concurrently (maximum parallelism)"""
        if not self.groups:
            return {}
        
        async with AsyncTimingContext("All Groups", self.debug):
            group_coroutines = [group.execute() for group in self.groups]
            group_results = await asyncio.gather(*group_coroutines, return_exceptions=True)
            
            all_results = {}
            for i, result in enumerate(group_results):
                if isinstance(result, Exception):
                    if self.debug:
                        sys.stderr.write(f"[DEBUG] Group {self.groups[i].name} failed: {result}\n")
                    all_results[f"group_{i}_error"] = str(result)
                elif isinstance(result, dict):
                    all_results.update(result)
            
            return all_results
    
    def clear_groups(self):
        """Clear all groups"""
        self.groups.clear()


class AsyncProcessingStrategy:
    """
    Defines different strategies for organizing operations into concurrent groups.
    
    This class provides predefined grouping strategies that organize GPS toolkit
    operations based on their dependencies and independence.
    """
    
    @staticmethod
    def get_parallel_groups() -> List[List[str]]:
        """
        Get the standard parallel processing groups for GPS toolkit operations.
        
        Returns:
            List of operation groups that can run concurrently:
            - Group 1: Core location data (location + weather + elevation)
            - Group 2: Image analysis (faces + QR + OCR + colors)
            - Group 3: Location-based data (venues + POIs + holidays + events)
            - Group 4: Web content (depends on URLs from Group 2)
        """
        return [
            # Group 1: Core location data - can start immediately with GPS coordinates
            ['location', 'weather', 'elevation'],
            
            # Group 2: Image analysis - independent of location, can run in parallel
            ['faces', 'qr', 'ocr', 'colors'],
            
            # Group 3: Location-based enrichment - needs location data from Group 1
            ['venues', 'pois', 'holidays', 'events'],
            
            # Group 4: Web content - needs URLs from OCR/QR in Group 2
            ['web_content']
        ]
    
    @staticmethod
    def get_maximal_parallel_groups() -> List[List[str]]:
        """
        Get maximum parallelism grouping (each operation in its own group).
        
        This provides the highest concurrency but may overwhelm APIs or resources.
        """
        return [
            ['location'],
            ['weather'],
            ['elevation'],
            ['faces'],
            ['qr'],
            ['ocr'],
            ['colors'],
            ['venues'],
            ['pois'],
            ['holidays'],
            ['events'],
            ['web_content']
        ]
    
    @staticmethod
    def get_conservative_groups() -> List[List[str]]:
        """
        Get conservative grouping for systems with limited resources.
        
        This reduces concurrency to be gentler on APIs and system resources.
        """
        return [
            # Group 1: Essential data
            ['location', 'weather'],
            
            # Group 2: Image analysis
            ['faces', 'ocr'],
            
            # Group 3: Secondary analysis
            ['qr', 'colors'],
            
            # Group 4: Location enrichment
            ['elevation', 'pois'],
            
            # Group 5: Venues and events
            ['venues', 'holidays', 'events'],
            
            # Group 6: Web content
            ['web_content']
        ]