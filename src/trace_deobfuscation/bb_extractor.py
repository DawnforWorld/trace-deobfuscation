"""Basic-block extraction from trace records.

Splits a linear trace into basic blocks at control-flow boundaries,
deduplicates them, and optionally splits blocks that are entered
at internal addresses (not at the block's first instruction).
"""

from __future__ import annotations

from collections import defaultdict

from .models import BasicBlock, JumpType, Record


def extract_basic_blocks(records: list[Record]) -> set[BasicBlock]:
    """Extract and deduplicate basic blocks from trace records.

    Walk the trace sequentially: collect records until a control-flow
    instruction is hit, then emit a ``BasicBlock``.  The same block may
    appear multiple times in the trace; a ``set`` guarantees uniqueness
    via ``BasicBlock.__hash__`` / ``__eq__``.

    Args:
        records: List of parsed trace Records in execution order.

    Returns:
        A deduplicated set of BasicBlock objects.
    """
    bbs: set[BasicBlock] = set()
    buf: list[Record] = []

    for record in records:
        buf.append(record)

        if record.is_control_flow:
            bb = BasicBlock(records=list(buf))
            bbs.add(bb)
            buf = []

    # If trace ends without a control-flow instruction (shouldn't happen,
    # but handle gracefully)
    if buf:
        bb = BasicBlock(records=list(buf))
        bbs.add(bb)

    return bbs


def split_blocks_at_targets(bbs: set[BasicBlock]) -> set[BasicBlock]:
    """Split basic blocks that are entered at an internal address.

    If any jump/call target points into the *middle* of a basic block,
    split that block into two at the target address so that every
    target aligns with a block entry.

    Args:
        bbs: The deduplicated set of basic blocks.

    Returns:
        A new set possibly containing split blocks.
    """
    # Build address → block lookup
    addr_to_bb: dict[int, BasicBlock] = {}
    for bb in bbs:
        for r in bb.records:
            addr_to_bb[r.address] = bb

    # Collect all direct targets
    targets: set[int] = set()
    for bb in bbs:
        if bb.direct_target is not None:
            targets.add(bb.direct_target)

    # Also collect indirect targets from trace context (not yet implemented)
    # For now, only handle direct targets.

    result: set[BasicBlock] = set()
    modified = False

    for bb in bbs:
        # Find the earliest target address that falls inside this block
        split_addrs = sorted(
            t for t in targets
            if any(r.address == t for r in bb.records)
            and t != bb.start_address
        )
        if not split_addrs:
            result.add(bb)
            continue

        modified = True
        # Split at each target address
        prev_addr = bb.start_address
        current_buf: list[Record] = []

        for r in bb.records:
            if r.address in split_addrs and current_buf:
                result.add(BasicBlock(records=list(current_buf)))
                current_buf = []
            current_buf.append(r)

        if current_buf:
            result.add(BasicBlock(records=list(current_buf)))

    return result


def extract_and_split(records: list[Record]) -> set[BasicBlock]:
    """Convenience: extract basic blocks, then split at internal targets.

    Args:
        records: List of parsed trace Records in execution order.

    Returns:
        Deduplicated, split-corrected set of BasicBlock objects.
    """
    bbs = extract_basic_blocks(records)
    return split_blocks_at_targets(bbs)
