"""Resolve data paths independently of the location of a feature module."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def data_root() -> Path:
    return (
        Path(os.environ.get('ACCORD_DATA_DIR', PROJECT_ROOT / '.local' / 'workspace'))
        .expanduser()
        .resolve()
    )


def database_path() -> Path:
    return data_root() / 'data' / 'pool.db'
