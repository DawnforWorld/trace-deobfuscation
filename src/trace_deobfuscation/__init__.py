"""Trace deobfuscation — VMP 3.9.4 obfuscation removal toolkit."""

__version__ = "0.1.0"

from .models import BasicBlock, Edge, EdgeType, JumpType, MemAccess, Record
from .parser import parse_trace
from .bb_extractor import extract_basic_blocks, extract_and_split
from .cfg_builder import build_cfg
from .merger import iterative_merge
from .visualizer import draw_cfg, draw_cfg_before_after

__all__ = [
    "__version__",
    "BasicBlock",
    "Edge",
    "EdgeType",
    "JumpType",
    "Record",
    "parse_trace",
    "extract_basic_blocks",
    "extract_and_split",
    "build_cfg",
    "iterative_merge",
    "draw_cfg",
    "draw_cfg_before_after",
]
