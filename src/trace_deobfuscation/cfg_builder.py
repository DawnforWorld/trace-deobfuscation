"""Control-flow graph builder.

Constructs edges (successor / predecessor relationships) across the
deduplicated set of basic blocks extracted from a trace.
"""

from __future__ import annotations

from .models import BasicBlock, Edge, EdgeType, JumpType


def build_cfg(bbs: set[BasicBlock], records: list) -> list[Edge]:
    """Build the full CFG: populate each BasicBlock's successors/predecessors.

    Strategy:
    1. Build an address → block lookup table.
    2. For each block, determine successors from its jump type.
    3. Register the reverse (predecessor) edges automatically.

    Args:
        bbs: Deduplicated basic blocks.
        records: Original parsed trace records with register state
                 (used to resolve indirect-jump targets observed at runtime).

    Returns:
        List of all Edge objects created.
    """
    # ------------------------------------------------------------------
    # Address → block lookup
    # ------------------------------------------------------------------
    addr_to_bb: dict[int, BasicBlock] = {}
    for bb in bbs:
        addr_to_bb[bb.start_address] = bb

    edges: list[Edge] = []

    def _add_edge(src: BasicBlock, tgt: BasicBlock, etype: EdgeType) -> Edge:
        e = Edge(source=src, target=tgt, edge_type=etype)
        src.successors.append(e)
        tgt.predecessors.append(e)
        edges.append(e)
        return e

    for bb in bbs:
        jt = bb.jump_type
        target = bb.direct_target

        if jt == JumpType.JMP:
            # Unconditional direct jump
            if target and target in addr_to_bb:
                _add_edge(bb, addr_to_bb[target], EdgeType.DIRECT_UNCOND)

        elif jt == JumpType.JCC:
            # Conditional jump: two successors
            # (a) The taken branch
            taken_bb = None
            if target and target in addr_to_bb:
                taken_bb = addr_to_bb[target]
                _add_edge(bb, taken_bb, EdgeType.DIRECT_COND_TAKEN)
            # (b) Fallthrough — use trace order (more reliable than
            #     address-based for VMP-obfuscated code with gaps).
            tgt_bb = _find_trace_successor(bb, records, addr_to_bb)
            if tgt_bb and tgt_bb is not taken_bb:
                _add_edge(bb, tgt_bb, EdgeType.DIRECT_COND_NOT_TAKEN)

        elif jt == JumpType.CALL:
            if target and target in addr_to_bb:
                _add_edge(bb, addr_to_bb[target], EdgeType.CALL)
            # Fallthrough after call (return address)
            fallthrough_addr = _compute_fallthrough(bb)
            if fallthrough_addr and fallthrough_addr in addr_to_bb:
                _add_edge(bb, addr_to_bb[fallthrough_addr], EdgeType.FALLTHROUGH)

        elif jt == JumpType.INDIRECT_JMP:
            # Resolve from trace: the record following the indirect jmp in
            # the trace is where execution actually went.
            tgt_bb = _find_trace_successor(bb, records, addr_to_bb)
            if tgt_bb:
                _add_edge(bb, tgt_bb, EdgeType.INDIRECT)

        elif jt == JumpType.INDIRECT_CALL:
            tgt_bb = _find_trace_successor(bb, records, addr_to_bb)
            if tgt_bb:
                _add_edge(bb, tgt_bb, EdgeType.CALL)
            # Fallthrough
            fallthrough_addr = _compute_fallthrough(bb)
            if fallthrough_addr and fallthrough_addr in addr_to_bb:
                _add_edge(bb, addr_to_bb[fallthrough_addr], EdgeType.FALLTHROUGH)

        elif jt == JumpType.RET:
            # ret — might return to a recorded address in trace
            tgt_bb = _find_trace_successor(bb, records, addr_to_bb)
            if tgt_bb:
                _add_edge(bb, tgt_bb, EdgeType.FALLTHROUGH)

        elif jt == JumpType.NORMAL:
            # No explicit control flow — look up the trace successor.
            tgt_bb = _find_trace_successor(bb, records, addr_to_bb)
            if tgt_bb:
                _add_edge(bb, tgt_bb, EdgeType.FALLTHROUGH)

    return edges


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_fallthrough(bb: BasicBlock) -> int | None:
    """Estimate fallthrough address of the last instruction in a block.

    Parses instruction bytes to compute: next_addr = last_addr + instruction_size.
    """
    if not bb.records:
        return None
    last = bb.records[-1]
    size = _instruction_size(last.bytes_hex)
    if size == 0:
        return None
    return last.address + size


def _instruction_size(bytes_hex: str) -> int:
    """Return the byte-length of an instruction from its hex byte string."""
    if not bytes_hex.strip():
        return 0
    return len(bytes_hex.split())


def _find_trace_successor(
    bb: BasicBlock,
    records: list,
    addr_to_bb: dict[int, BasicBlock],
) -> BasicBlock | None:
    """Find the block that follows *bb* in the original trace order.

    For indirect jumps, the next executed instruction in the trace tells us
    the runtime target.  We search for the first record whose address differs
    from the last record of *bb*, then look up its containing block.
    """
    if not bb.records or not records:
        return None
    last_addr = bb.records[-1].address

    # Find the position of the last record in the trace
    try:
        idx = next(
            i for i, r in enumerate(records)
            if r.address == last_addr
            and r.bytes_hex == bb.records[-1].bytes_hex
        )
    except StopIteration:
        return None

    # Look for the next record with a different address
    for i in range(idx + 1, len(records)):
        if records[i].address != last_addr:
            return addr_to_bb.get(records[i].address)
    return None
