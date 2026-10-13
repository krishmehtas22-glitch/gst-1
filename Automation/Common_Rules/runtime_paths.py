"""Keep invoice data beside the executable, never inside a frozen bundle."""
from pathlib import Path
import sys


def default_data_root(script_path):
    if getattr(sys,'frozen',False):return Path(sys.executable).resolve().parent
    return Path(script_path).resolve().parent
