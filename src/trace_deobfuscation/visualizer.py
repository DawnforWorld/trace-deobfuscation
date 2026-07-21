"""CFG visualization using Graphviz.

Renders the control-flow graph as a PNG/SVG/PDF, with different edge styles
for each edge type following the conventions from the article.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import graphviz

from .models import BasicBlock, EdgeType

# Edge style mapping (following the article's conventions)
_EDGE_STYLES: dict[EdgeType, dict] = {
    EdgeType.DIRECT_UNCOND: {
        "color": "blue",
        "style": "solid",
        "label": "jmp",
    },
    EdgeType.DIRECT_COND_TAKEN: {
        "color": "green",
        "style": "dashed",
        "label": "jcc taken",
    },
    EdgeType.DIRECT_COND_NOT_TAKEN: {
        "color": "red",
        "style": "dashed",
        "label": "jcc ~taken",
    },
    EdgeType.INDIRECT: {
        "color": "orange",
        "style": "solid",
        "label": "indirect",
    },
    EdgeType.CALL: {
        "color": "purple",
        "style": "dotted",
        "label": "call",
    },
    EdgeType.FALLTHROUGH: {
        "color": "black",
        "style": "solid",
        "label": "fall",
    },
}


def draw_cfg(
    bbs: set[BasicBlock],
    output_path: str | Path = "output/cfg",
    fmt: str = "png",
    *,
    title: Optional[str] = None,
    view: bool = False,
) -> Path:
    """Render the CFG of a set of basic blocks with Graphviz.

    Args:
        bbs: The set of basic blocks to draw.
        output_path: Base path for the output file (without extension).
        fmt: Output format — 'png', 'svg', 'pdf', 'dot', etc.
        title: Optional graph title.
        view: If True, open the rendered image.

    Returns:
        Path to the generated file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    dot = graphviz.Digraph(
        name="cfg",
        format=fmt,
        node_attr={
            "shape": "box",
            "style": "rounded,filled",
            "fillcolor": "#f0f0f0",
            "fontname": "Consolas",
            "fontsize": "10",
        },
        edge_attr={
            "fontname": "Consolas",
            "fontsize": "8",
        },
        graph_attr={
            "rankdir": "TB",
            "dpi": "150",
        },
    )

    if title:
        dot.attr(label=title, labelloc="t", fontsize="14")

    # Add nodes
    for bb in bbs:
        node_id = _node_id(bb)
        label = _node_label(bb)
        dot.node(node_id, label)

    # Add edges (deduplicate by source→target pair)
    seen_edges: set[tuple[str, str]] = set()
    for bb in bbs:
        src_id = _node_id(bb)
        for edge in bb.successors:
            tgt_id = _node_id(edge.target)
            key = (src_id, tgt_id)
            if key in seen_edges:
                # Multiple edge types between the same pair — append
                continue
            seen_edges.add(key)

            style = _EDGE_STYLES.get(edge.edge_type, _EDGE_STYLES[EdgeType.FALLTHROUGH])
            dot.edge(
                src_id,
                tgt_id,
                color=style["color"],
                style=style["style"],
                label=style["label"],
                fontcolor=style["color"],
            )

    # Render
    rendered = dot.render(filename=str(output_path), cleanup=True, view=view)

    return Path(rendered)


def _node_id(bb: BasicBlock) -> str:
    """Unique graphviz node ID for a basic block."""
    return f"bb_{bb.start_address:X}"


def _node_label(bb: BasicBlock) -> str:
    """Graphviz node label — first/last instruction + count."""
    if not bb.records:
        return "???"

    first = bb.records[0]
    last = bb.records[-1]
    size = bb.size

    lines = [
        f"0x{first.address:X} [{size} insns]",
        "─" * 30,
    ]
    # Show first 5 and last 2 instructions
    max_show = 5
    for i, r in enumerate(bb.records):
        if i >= max_show and i < size - 2:
            if i == max_show:
                lines.append(f"  ... ({size - max_show - 2} more)")
            continue
        lines.append(f"  {r.disasm}")

    return "\n".join(lines)


def draw_cfg_before_after(
    before: set[BasicBlock],
    after: set[BasicBlock],
    output_dir: str | Path = "output",
    fmt: str = "png",
) -> tuple[Path, Path]:
    """Render before/after CFG comparison (pre-merge vs post-merge).

    Args:
        before: Original basic blocks.
        after: Merged basic blocks.
        output_dir: Directory for output files.
        fmt: Output format.

    Returns:
        (before_path, after_path).
    """
    output_dir = Path(output_dir)
    before_path = draw_cfg(
        before,
        output_dir / "cfg_before",
        fmt=fmt,
        title="CFG — Before Merging",
    )
    after_path = draw_cfg(
        after,
        output_dir / "cfg_after",
        fmt=fmt,
        title="CFG — After Merging",
    )
    return before_path, after_path
