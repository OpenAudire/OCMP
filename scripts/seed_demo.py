#!/usr/bin/env python3
"""Seed the database with demo data.

Usage:
    python scripts/seed_demo.py

This script loads the demo dataset including:
- Demo institution
- BSc Health Sciences (Demo) programme
- 3 modules with ~20 learning events
- ~60 objectives
- Demo Graduate Competencies framework
- Bloom and Miller taxonomy scales
- Sample tag lists
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


async def main() -> None:
    """Load demo data into the database."""
    print("Demo seed script - implementation pending")
    print("This will be implemented in Slice 0.18")


if __name__ == "__main__":
    asyncio.run(main())
