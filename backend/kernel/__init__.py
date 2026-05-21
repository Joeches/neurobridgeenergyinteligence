"""
NeuroBridge 11D - Kernel Module
Exports kernel wrapper for external use
"""

from backend.kernel_loader import get_kernel_loader, kernel, kernel_loader

__all__ = [
    'get_kernel_loader',
    'kernel',
    'kernel_loader'
]