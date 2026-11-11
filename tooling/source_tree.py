"""Production source discovery excludes local data assets and tool caches."""
from fnmatch import fnmatch
import os
from pathlib import Path


def repository_files(root: Path, pattern: str = '*'):
    """Yield repository text candidates without traversing local asset trees."""
    root = Path(root)
    for current, directories, names in os.walk(root):
        directories[:] = [name for name in directories if name not in {
            'assets', '__pycache__', 'node_modules', '.git', '.cache', 'runtime',
        }]
        if root.name == 'assets':
            directories[:] = []
        for name in names:
            if fnmatch(name, pattern):
                yield Path(current) / name


def python_sources(root: Path):
    """Yield application Python files, excluding Python stored as local evidence."""
    yield from repository_files(root, '*.py')
