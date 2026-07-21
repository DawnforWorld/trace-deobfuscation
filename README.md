# trace-deobfuscation

VMP 3.9.4 混淆的 trace 反混淆工具。基于 Intel Pin 生成的指令级 trace 数据，通过基本块提取、CFG 构建、基本块合并等方式，逐步解除 VMP 的代码乱序混淆。

---

## 环境要求

| 项目 | 最低版本 |
|------|---------|
| Python | 3.14+ |
| uv | 0.11+ |
| Graphviz | 15.x（可选，仅可视化需要） |

---

## 搭建

```bash
# 1. 克隆项目
git clone <repo-url> trace-deobfuscation
cd trace-deobfuscation

# 2. 安装 uv（如果没有）
#    Windows: winget install --id=astral-sh.uv -e
#    macOS/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. 创建虚拟环境 + 安装依赖（uv 自动完成）
uv sync

# 4. (可选) 安装 Graphviz，用于渲染 CFG 图
#    Windows: winget install Graphviz.Graphviz
#    macOS:   brew install graphviz
#    Linux:   sudo apt install graphviz

# 5. 验证
uv run trace-deobf --help
```

不需要手动 `pip install`，`uv sync` 自动根据 `pyproject.toml` 和 `uv.lock` 创建隔离的 `.venv` 并安装所有依赖。

---

## 使用

### 基本用法

```bash
uv run trace-deobf <trace文件.jsonl>
```

### 跳过可视化（Graphviz 未安装时）

```bash
uv run trace-deobf data/sample.jsonl --no-graph
```

### 指定输出目录

```bash
uv run trace-deobf data/trace.jsonl -o my_output
```

### 输出文件

| 文件 | 内容 |
|------|------|
| `output/cfg_before.png` | 合并前的控制流图 |
| `output/cfg_after.png` | 合并后的控制流图 |

### 控制台输出示例

```
[1/5] Parsing trace: data/sample.jsonl
      Parsed 7 records
[2/5] Extracting basic blocks ...
      3 unique basic blocks
      Types: 1 JMP, 1 JCC, 1 indirect, 0 CALL, 0 RET
      Total instructions across all blocks: 7
[3/5] Building CFG edges ...
      2 edges created
[4/5] Merging basic blocks (code-layout deobfuscation) ...
      1 merges performed
      2 blocks remaining (was 3)
      Types: 0 JMP, 1 JCC, 1 indirect
      Average block size: 3.5 instructions
[5/5] Rendering CFG graphs ...
      Before: output/cfg_before.png
      After:  output/cfg_after.png

============================================================
Summary:
  Trace records:    7
  Original blocks:  4
  Merged blocks:    3
  Merges:           1
  Reduction:        1 blocks (25.0%)
============================================================
```

### 摘要字段说明

| 字段 | 含义 |
|------|------|
| Trace records | 成功解析的 trace 指令条数 |
| Original blocks | 去重后的基本块数量 |
| Merged blocks | 合并后的基本块数量 |
| Merges | 执行的合并操作次数 |
| Reduction | 基本块减少比例（越大说明代码乱序越严重） |

---

## 项目结构

```
trace-deobfuscation/
├── pyproject.toml              # uv 项目配置，入口: trace-deobf
├── uv.lock                     # 锁定的依赖版本
├── README.md                   # 本文件
├── docs/
│   └── trace-format-spec.md    # Trace 文件格式规范
├── data/
│   └── sample.jsonl            # Pin 格式样本
├── scripts/
│   ├── __init__.py
│   └── run.py                  # 备用入口脚本
├── src/trace_deobfuscation/
│   ├── __init__.py             # 包入口
│   ├── cli.py                  # 命令行入口
│   ├── models.py               # 数据模型: Record / BasicBlock / Edge
│   ├── parser.py               # Pin JSON Lines 解析器
│   ├── bb_extractor.py         # 基本块提取 + 内部目标切分
│   ├── cfg_builder.py          # CFG 边构建
│   ├── merger.py               # 基本块合并（代码乱序反混淆）
│   └── visualizer.py           # Graphviz 可视化
└── output/                     # 渲染输出目录
```

### 数据流

```
trace 文件 (.jsonl)
       │
       ▼  parser.py
  list[Record]          ← 每条指令的地址、字节码、反汇编、寄存器、内存读写
       │
       ▼  bb_extractor.py
  set[BasicBlock]       ← 按控制流边界切分 + set 去重
       │
       ▼  cfg_builder.py
  list[Edge]            ← 填好每个块的前驱/后继
       │
       ▼  merger.py
  set[BasicBlock]       ← 合并无条件跳转连接的 1:1 块对
       │
       ▼  visualizer.py
  output/cfg_*.png      ← 合并前后的 CFG 图
```

---

## Trace 文件格式

详见 [`docs/trace-format-spec.md`](docs/trace-format-spec.md)。

简而言之：Intel Pin pintool 产出的 **JSON Lines** 格式，每行一条指令，包含地址、字节码、反汇编、执行前寄存器状态、内存读写和目标地址等。

---

## 文档

- [Trace 文件格式规范](docs/trace-format-spec.md) — Pin 输出格式要求
