"""
Setup for NeuroBridge Kernel - Works with current Python environment
"""

from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
import pybind11
import sys
import os

# Get current Python paths
python_include = sys.prefix + '/include'
python_lib = sys.prefix + '/libs'

extra_compile_args = [
    '-O3',
    '-Wall', 
    '-std=c++17',
    '-ffast-math',
    '-DNDEBUG',
]

extra_link_args = [
    '-shared',
]

kernel_module = Extension(
    '_kernel_compiled',
    sources=['bindings.cpp', 'core.cpp'],
    include_dirs=[
        pybind11.get_include(),
        '.',
        python_include,
    ],
    library_dirs=[python_lib],
    language='c++',
    extra_compile_args=extra_compile_args,
    extra_link_args=extra_link_args,
)

class BuildExt(build_ext):
    def build_extensions(self):
        super().build_extensions()
        
        from pathlib import Path
        import shutil
        
        for ext in self.extensions:
            ext_name = ext.name
            build_dir = Path(self.build_lib)
            for file in build_dir.rglob(f'{ext_name}*.pyd'):
                if file.exists():
                    print(f"\n✅ Compiled: {file}")
                    shutil.copy2(file, Path.cwd() / f'{ext_name}.pyd')
                    shutil.copy2(file, Path.cwd().parent / f'{ext_name}.pyd')
                    shutil.copy2(file, Path.cwd().parent / '_kernel.pyd')
                    break

setup(
    name='neurobridge_kernel',
    version='13.0.0',
    ext_modules=[kernel_module],
    cmdclass={'build_ext': BuildExt},
)