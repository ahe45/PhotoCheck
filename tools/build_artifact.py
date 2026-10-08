"""Resolve the versioned build output without importing application dependencies."""
from pathlib import Path
import runpy


def executable_path(root):
    root = Path(root)
    version = runpy.run_path(str(root / 'photocheck' / '__init__.py'))['__version__']
    return root / 'dist' / f'PhotoCheck_{version}.exe'
