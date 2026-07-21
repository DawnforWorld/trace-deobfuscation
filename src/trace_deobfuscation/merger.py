"""Basic-block merger — resolves code-layout obfuscation.

Iteratively merges basic blocks that are connected by unconditional
direct jumps and form a simple linear chain (1:1 successor/predecessor).
"""

from __future__ import annotations

from .models import BasicBlock, Edge, EdgeType, JumpType


def can_merge(a: BasicBlock, b: BasicBlock, edge: Edge) -> bool:
    """Check whether two basic blocks *a* → *b* are eligible for merging.

    Conditions (following the article):
    1. *a* has exactly one successor (i.e. no branching at the end).
    2. *b* has exactly one predecessor (i.e. no merge point).
    3. The connecting edge is a DIRECT_UNCOND jump.

    Args:
        a: Source basic block.
        b: Target basic block.
        edge: The edge connecting a → b.

    Returns:
        True if the pair can be merged into a single block.
    """
    if edge.edge_type != EdgeType.DIRECT_UNCOND:
        return False
    if len(a.successors) != 1:
        return False
    if len(b.predecessors) != 1:
        return False
    return True


def merge_two(a: BasicBlock, b: BasicBlock, connecting_edge: Edge) -> BasicBlock:
    """Merge *b* into *a*, producing a new ``BasicBlock``.

    The new block:
    - Contains *a*'s instructions followed by *b*'s.
    - Adopts *b*'s jump_type and direct_target.
    - Inherits *a*'s predecessors and *b*'s successors.
    - The original *a* and *b* remain unchanged (immutable style).

    Args:
        a: Source block.
        b: Target block to be absorbed.
        connecting_edge: The edge a → b that triggers the merge.

    Returns:
        A new merged BasicBlock.
    """
    merged_records = list(a.records) + list(b.records)
    merged = BasicBlock(
        records=merged_records,
        jump_type=b.jump_type,
        direct_target=b.direct_target,
    )
    merged.merged = True

    # Rebuild edges: inherit a's predecessors and b's successors
    for pred_edge in a.predecessors:
        if pred_edge is connecting_edge:
            continue
        new_edge = Edge(
            source=pred_edge.source,
            target=merged,
            edge_type=pred_edge.edge_type,
        )
        merged.predecessors.append(new_edge)
        pred_edge.source.successors = [
            new_edge if s is connecting_edge or s.target is a else s
            for s in pred_edge.source.successors
        ]

    for succ_edge in b.successors:
        new_edge = Edge(
            source=merged,
            target=succ_edge.target,
            edge_type=succ_edge.edge_type,
        )
        merged.successors.append(new_edge)
        succ_edge.target.predecessors = [
            new_edge if p is connecting_edge or p.source is b else p
            for p in succ_edge.target.predecessors
        ]

    return merged


def iterative_merge(bbs: set[BasicBlock]) -> tuple[set[BasicBlock], int]:
    """Iteratively merge basic blocks until no more merges are possible.

    Merges blocks connected via DIRECT_UNCOND edges in a 1:1 relationship.
    The loop continues as long as at least one merge succeeded in the
    previous round (following the article's ``keepRun`` pattern).

    Args:
        bbs: The current set of deduplicated basic blocks.

    Returns:
        (new_bbs, total_merges) — the merged set and the number of
        merges performed.
    """
    current = set(bbs)
    total_merges = 0

    while True:
        changed = False
        merged_set: set[BasicBlock] = set()
        merged_ids: set[int] = set()  # track merged blocks by id

        # Build a work-list of mergeable pairs
        pairs: list[tuple[BasicBlock, BasicBlock, Edge]] = []
        for bb in current:
            if len(bb.successors) != 1:
                continue
            succ_edge = bb.successors[0]
            if succ_edge.edge_type != EdgeType.DIRECT_UNCOND:
                continue
            succ = succ_edge.target
            if len(succ.predecessors) != 1:
                continue
            pairs.append((bb, succ, succ_edge))

        if not pairs:
            break

        # Perform merges — block may only participate in one merge per round
        processed: set[int] = set()
        for a, b, e in pairs:
            if id(a) in processed or id(b) in processed:
                continue
            merged = merge_two(a, b, e)
            merged_set.add(merged)
            processed.add(id(a))
            processed.add(id(b))
            changed = True
            total_merges += 1

        # Add blocks that were not merged
        for bb in current:
            if id(bb) not in processed:
                merged_set.add(bb)

        if not changed:
            break
        current = merged_set

    return current, total_merges
