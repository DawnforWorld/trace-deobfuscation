"""Data models for trace deobfuscation.

Defines the core types: Record (trace instruction), BasicBlock (grouped
instructions with control-flow info), Edge (CFG edge), and enumerations for
jump types and edge types.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class JumpType(Enum):
    """Classifies the last instruction of a basic block."""

    NORMAL = auto()          # 普通指令结尾 (非控制流)
    JMP = auto()             # 无条件直接跳转 (jmp imm)
    JCC = auto()             # 条件跳转 (jcc imm)
    CALL = auto()            # 直接调用 (call imm)
    RET = auto()             # 返回 (ret)
    INDIRECT_JMP = auto()    # 间接跳转 (jmp reg/mem)
    INDIRECT_CALL = auto()   # 间接调用 (call reg/mem)


class EdgeType(Enum):
    """Classifies the type of control-flow edge between two basic blocks."""

    DIRECT_UNCOND = auto()         # 无条件直接跳转 (蓝色实线)
    DIRECT_COND_TAKEN = auto()     # 条件跳转 — 跳转成立 (绿色虚线)
    DIRECT_COND_NOT_TAKEN = auto() # 条件跳转 — 跳转不成立 / fallthrough (红色虚线)
    INDIRECT = auto()              # 间接跳转
    CALL = auto()                  # 直接调用
    FALLTHROUGH = auto()           # 自然落到下一个基本块 (黑色实线)


@dataclass
class MemAccess:
    """A single memory read or write observed during instruction execution.

    Attributes:
        address: 被访问的内存地址 (整数).
        size: 访问字节数.
        value: 读取到/写入的值 (整数).
    """

    address: int
    size: int
    value: int


@dataclass
class Record:
    """A single trace instruction record.

    Attributes:
        address: 指令地址 (整数).
        bytes_hex: 指令字节码 (hex 字符串, e.g. "48 89 5C 24 08").
        disasm: 反汇编文本.
        registers: 执行前通用寄存器值 dict, key 为大写寄存器名.
        rflags: 执行前标志寄存器值 (整数).
        mem_reads: 本条指令读取的内存列表 (Pin IARG_MEMORYREAD_EA).
        mem_writes: 本条指令写入的内存列表 (Pin IARG_MEMORYWRITE_EA).
        branch_taken: 若为条件分支指令, 记录实际走向 (True=taken, False=not-taken,
                      None=不是分支指令或无此信息).
        thread_id: 执行线程 ID (Pin IARG_THREAD_ID).
        comment: 可选注释.
    """

    address: int
    bytes_hex: str
    disasm: str
    registers: dict[str, int] = field(default_factory=dict)
    rflags: int = 0
    mem_reads: list[MemAccess] = field(default_factory=list)
    mem_writes: list[MemAccess] = field(default_factory=list)
    branch_taken: Optional[bool] = None
    thread_id: int = 0
    comment: str = ""

    def __hash__(self) -> int:
        return hash((self.address, self.bytes_hex, self.disasm))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Record):
            return NotImplemented
        return (
            self.address == other.address
            and self.bytes_hex == other.bytes_hex
            and self.disasm == other.disasm
        )

    @property
    def is_control_flow(self) -> bool:
        """判断这条指令是否是控制流指令 (jmp / jcc / call / ret)."""
        mnemonic = self._mnemonic()
        return mnemonic in _CONTROL_FLOW_MNEMONICS

    @property
    def is_indirect(self) -> bool:
        """判断是否是间接跳转/调用."""
        mnemonic = self._mnemonic()
        if mnemonic not in ("jmp", "call"):
            return False
        # 间接: 操作数不是立即数 (e.g. jmp rax / jmp [rdx])
        return "0x" not in self.disasm.split(maxsplit=1)[-1]

    def get_jump_type(self) -> JumpType:
        """推断此指令的跳转类型."""
        mnemonic = self._mnemonic()
        indirect = self.is_indirect
        if mnemonic == "jmp":
            return JumpType.INDIRECT_JMP if indirect else JumpType.JMP
        if mnemonic in _JCC_MNEMONICS:
            return JumpType.JCC
        if mnemonic == "call":
            return JumpType.INDIRECT_CALL if indirect else JumpType.CALL
        if mnemonic == "ret":
            return JumpType.RET
        return JumpType.NORMAL

    def get_direct_target(self) -> Optional[int]:
        """若为直接跳转/调用，返回目标地址；否则返回 None."""
        mnemonic = self._mnemonic()
        if mnemonic not in ("jmp", "call") and mnemonic not in _JCC_MNEMONICS:
            return None
        if self.is_indirect:
            return None
        # 尝试从 disasm 中提取立即数
        match = re.search(r"(0x[0-9a-fA-F]+)", self.disasm)
        if match:
            return int(match.group(1), 16)
        return None

    def _mnemonic(self) -> str:
        """提取反汇编中的助记符 (小写)."""
        return self.disasm.strip().split(maxsplit=1)[0].lower()

    def __repr__(self) -> str:
        return f"Record(0x{self.address:X}, {self.disasm!r})"


# 控制流指令助记符集合
_CONTROL_FLOW_MNEMONICS = frozenset({
    "jmp", "call", "ret", "retn",
    "ja", "jae", "jb", "jbe", "jc", "je", "jg", "jge",
    "jl", "jle", "jna", "jnae", "jnb", "jnbe", "jnc", "jne",
    "jng", "jnge", "jnl", "jnle", "jno", "jnp", "jns", "jnz",
    "jo", "jp", "jpe", "jpo", "js", "jz", "jcxz", "jecxz", "jrcxz",
    "loop", "loope", "loopne", "loopnz", "loopz",
})

_JCC_MNEMONICS = frozenset({
    "ja", "jae", "jb", "jbe", "jc", "je", "jg", "jge",
    "jl", "jle", "jna", "jnae", "jnb", "jnbe", "jnc", "jne",
    "jng", "jnge", "jnl", "jnle", "jno", "jnp", "jns", "jnz",
    "jo", "jp", "jpe", "jpo", "js", "jz", "jcxz", "jecxz", "jrcxz",
    "loop", "loope", "loopne", "loopnz", "loopz",
})


@dataclass
class BasicBlock:
    """A basic block: a linear sequence of instructions with a single entry and exit.

    Hash / equality are based on the ordered list of instruction addresses,
    enabling set-based deduplication.
    """

    records: list[Record] = field(default_factory=list)
    jump_type: JumpType = JumpType.NORMAL
    direct_target: Optional[int] = None

    # 后继/前驱 — 在 CFG 构建阶段填入
    successors: list[Edge] = field(default_factory=list)
    predecessors: list[Edge] = field(default_factory=list)

    # 混淆标识 (由各个 processor 设置)
    obf_op_status: bool = False       # 不透明谓词状态
    obf_op_cond_taken: bool = False   # 不透明谓词的实际跳转事实
    obf_mem_const_hide_status: bool = False  # 内存操作数常量隐藏状态
    obf_mem_const_hide_detail: str = ""     # 内存操作数常量隐藏详情

    # 反混淆标记
    merged: bool = False              # 是否已被合并
    indirect_resolved: bool = False   # 间接跳转是否已被解析

    def __post_init__(self):
        if self.records and self.jump_type == JumpType.NORMAL:
            # 从最后一条指令推断跳转类型
            last = self.records[-1]
            if last.is_control_flow:
                self.jump_type = last.get_jump_type()
                self.direct_target = last.get_direct_target()

    @property
    def start_address(self) -> int:
        """基本块起始地址."""
        return self.records[0].address if self.records else 0

    @property
    def end_address(self) -> int:
        """基本块结束地址."""
        return self.records[-1].address if self.records else 0

    @property
    def size(self) -> int:
        """基本块指令数量."""
        return len(self.records)

    @property
    def address_signature(self) -> str:
        """基于指令地址序列的唯一标识 (用于去重)."""
        return ",".join(f"{r.address:X}" for r in self.records)

    def __hash__(self) -> int:
        # 用 SHA256 作为哈希 (替代文章里的 tuple hash, 避免大数据量碰撞)
        digest = hashlib.sha256(self.address_signature.encode()).digest()
        return int.from_bytes(digest[:8], "big")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BasicBlock):
            return NotImplemented
        return self.address_signature == other.address_signature

    def __repr__(self) -> str:
        start = f"0x{self.start_address:X}" if self.records else "?"
        return f"BB({start}, {self.size} insns, {self.jump_type.name})"


@dataclass
class Edge:
    """A control-flow edge connecting two basic blocks."""

    source: BasicBlock
    target: BasicBlock
    edge_type: EdgeType

    def __hash__(self) -> int:
        return hash((id(self.source), id(self.target), self.edge_type))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Edge):
            return NotImplemented
        return (
            self.source is other.source
            and self.target is other.target
            and self.edge_type is other.edge_type
        )

    def __repr__(self) -> str:
        src = f"0x{self.source.start_address:X}" if self.source.records else "?"
        tgt = f"0x{self.target.start_address:X}" if self.target.records else "?"
        return f"Edge({src} -> {tgt}, {self.edge_type.name})"
