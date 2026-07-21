"""CLI entry point for the trace-deobf command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .bb_extractor import extract_and_split
from .cfg_builder import build_cfg
from .merger import iterative_merge
from .models import JumpType
from .parser import parse_trace


def main() -> int:
    parser = argparse.ArgumentParser(
        description="VMP 3.9.4 trace deobfuscation — basic block merging pipeline",
    )
    parser.add_argument(
        "trace_file",
        help="Path to the Intel Pin JSON Lines trace file",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="output",
        help="Output directory for graphs (default: output/)",
    )
    parser.add_argument(
        "--no-graph",
        action="store_true",
        help="Skip graph rendering (useful when Graphviz is not installed)",
    )
    args = parser.parse_args()

    trace_path = Path(args.trace_file)
    if not trace_path.exists():
        print(f"Error: trace file not found: {args.trace_file}")
        return 1

    # ------------------------------------------------------------------
    # Step 1: Parse
    # ------------------------------------------------------------------
    print(f"[1/5] Parsing trace: {trace_path}")
    try:
        records = parse_trace(str(trace_path))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(f"      Parsed {len(records)} records")

    if not records:
        print("      Warning: no records found — is the file valid JSON Lines?")

    # ------------------------------------------------------------------
    # Step 2: Extract basic blocks
    # ------------------------------------------------------------------
    print("[2/5] Extracting basic blocks ...")
    bbs = extract_and_split(records)
    print(f"      {len(bbs)} unique basic blocks")

    # Statistics
    jmp_blocks = sum(1 for bb in bbs if bb.jump_type == JumpType.JMP)
    jcc_blocks = sum(1 for bb in bbs if bb.jump_type == JumpType.JCC)
    ind_blocks = sum(1 for bb in bbs if bb.jump_type in (JumpType.INDIRECT_JMP, JumpType.INDIRECT_CALL))
    call_blocks = sum(1 for bb in bbs if bb.jump_type == JumpType.CALL)
    ret_blocks = sum(1 for bb in bbs if bb.jump_type == JumpType.RET)
    total_insns = sum(bb.size for bb in bbs)
    print(f"      Types: {jmp_blocks} JMP, {jcc_blocks} JCC, {ind_blocks} indirect, "
          f"{call_blocks} CALL, {ret_blocks} RET")
    print(f"      Total instructions across all blocks: {total_insns}")

    # ------------------------------------------------------------------
    # Step 3: Build CFG
    # ------------------------------------------------------------------
    print("[3/5] Building CFG edges ...")
    edges = build_cfg(bbs, records)
    print(f"      {len(edges)} edges created")

    # ------------------------------------------------------------------
    # Step 4: Merge basic blocks
    # ------------------------------------------------------------------
    print("[4/5] Merging basic blocks (code-layout deobfuscation) ...")
    bbs_before = set(bbs)  # snapshot for before/after graph
    merged_bbs, merge_count = iterative_merge(bbs)
    print(f"      {merge_count} merges performed")
    print(f"      {len(merged_bbs)} blocks remaining (was {len(bbs_before)})")

    # Statistics after merge
    jmp_after = sum(1 for bb in merged_bbs if bb.jump_type == JumpType.JMP)
    jcc_after = sum(1 for bb in merged_bbs if bb.jump_type == JumpType.JCC)
    ind_after = sum(1 for bb in merged_bbs if bb.jump_type in (JumpType.INDIRECT_JMP, JumpType.INDIRECT_CALL))
    avg_size = sum(bb.size for bb in merged_bbs) / max(len(merged_bbs), 1)
    print(f"      Types: {jmp_after} JMP, {jcc_after} JCC, {ind_after} indirect")
    print(f"      Average block size: {avg_size:.1f} instructions")

    # ------------------------------------------------------------------
    # Step 5: Visualize
    # ------------------------------------------------------------------
    if not args.no_graph:
        print("[5/5] Rendering CFG graphs ...")
        try:
            from .visualizer import draw_cfg_before_after
            before_path, after_path = draw_cfg_before_after(
                bbs_before, merged_bbs, output_dir=args.output_dir,
            )
            print(f"      Before: {before_path}")
            print(f"      After:  {after_path}")
        except Exception as exc:
            print(f"      Graph rendering failed: {exc}")
            print("      Hint: install Graphviz — https://graphviz.org/download/")
            print("      Or use --no-graph to skip rendering.")
    else:
        print("[5/5] Skipping graph rendering (--no-graph)")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("Summary:")
    print(f"  Trace records:    {len(records)}")
    print(f"  Original blocks:  {len(bbs_before)}")
    print(f"  Merged blocks:    {len(merged_bbs)}")
    print(f"  Merges:           {merge_count}")
    print(f"  Reduction:        {len(bbs_before) - len(merged_bbs)} blocks "
          f"({100 * (len(bbs_before) - len(merged_bbs)) / max(len(bbs_before), 1):.1f}%)")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
