"""
mppdp5 CLI - Command line interface for mppdp5 adapters.

Provides subcommands for each adapter:
- mppdp5 contour: Extract contour lines from video
- mppdp5 pose: Extract pose keypoints from video
- mppdp5 segment: Extract segmentation masks from video
- mppdp5 pipeline: Run full pipeline (contour + pose + segment)
"""

from .main import main

__all__ = ["main"]