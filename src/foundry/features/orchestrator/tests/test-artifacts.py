#!/usr/bin/env python3
"""Test script to remove and regenerate artifacts."""

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

# Step 1: Remove existing artifacts
artifacts_to_remove = [
    ".runtime",
    ".cache",
    ".artifacts",
    "data",
    "__pycache__",
    ".ruff_cache",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
    ".opencode/node_modules",
    "dist",
    "build",
    ".coverage",
    ".coverage.json",
    "htmlcov",
    "graphify-out",
    "*.egg-info",
    ".eggs",
    "*.log",
]

print("=== Removing existing artifacts ===")
for item in artifacts_to_remove:
    paths = list(PROJECT_ROOT.glob(item))
    for path in paths:
        try:
            if path.is_dir():
                shutil.rmtree(path)
                print(f"Removed directory: {path}")
            else:
                path.unlink()
                print(f"Removed file: {path}")
        except Exception as e:
            print(f"Failed to remove {path}: {e}")

# Step 2: Test regenerating some artifacts
print("\n=== Testing artifact regeneration ===")

# Import config and create .runtime directories
sys.path.insert(0, str(PROJECT_ROOT / "sdlc"))
from sdlc.config import settings

print("\nCreating runtime directories...")
settings.ensure_dirs()

# Check what was created
print("\n=== Checking created artifacts ===")
for dir_name in [".runtime", ".cache", ".artifacts"]:
    dir_path = PROJECT_ROOT / dir_name
    if dir_path.exists():
        print(f"\n{dir_name}/ exists! Contents:")
        for item in dir_path.iterdir():
            print(f"  - {item.name}")

# Also check sdlc directory contents
print("\nChecking sdlc directory:")
sdlc_dir = PROJECT_ROOT / "sdlc"
for item in sdlc_dir.iterdir():
    if item.name in ["__pycache__", ".ruff_cache", ".mypy_cache", ".pytest_cache", "data", ".runtime"]:
        print(f"  Found: {item.name}")
