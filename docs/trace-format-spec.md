# Intel Pin Trace JSON Lines 格式规范

适用于本项目的 trace 输入文件。每条指令一个完整的 JSON 对象，**一行就是一条记录**，文件中不得出现物理换行符（字符串内的换行须转义为 `\n`）。

---

## 顶层字段

| 字段 | 类型 | 必须 | 说明 |
|------|------|:---:|------|
| `addr` | string | ✓ | 指令地址，16 进制，大写，定宽 16 位，无 `0x` 前缀。例：`"00007FF730291133"` |
| `bytes` | string | ✓ | 机器码，大写 hex 对，空格分隔。例：`"48 8B 4F 08"` |
| `disasm` | string | ✓ | 反汇编文本。例：`"mov rcx, qword ptr [rdi+0x8]"` |
| `regs` | object | ✓ | 执行**前**的寄存器快照，可为 `{}` 或 `null` |
| `mem_r` | array | ✓ | 本指令读取的内存列表，空时为 `[]` 或 `null` |
| `mem_w` | array | ✓ | 本指令写入的内存列表，空时为 `[]` 或 `null` |
| `thread_id` | int\|null | | 执行线程 ID，没有则填 `0` 或 `null` |
| `branch_taken` | bool\|null | | 条件分支真实走向。不是分支指令填 `null` |
| `comment` | string\|null | | 注释，没有则填 `""` 或 `null` |

---

## `regs` 对象字段

key 为**大写**寄存器名，value 为 16 进制字符串，定宽 16 位。**必须包含 `EFLAGS`**。

| key | 类型 | 说明 |
|-----|------|------|
| `RAX` ~ `R15` | string | 通用寄存器 (x64: 16 个) |
| `EFLAGS` | string | 标志寄存器 |

```json
"regs": {
  "RAX": "0000000000000032",
  "RBX": "0000000000000002",
  "RCX": "00000000FFFFFFFF",
  "RSP": "000000000014FEC0",
  "EFLAGS": "0000000000000202"
}
```

---

## `mem_r` / `mem_w` 数组元素

| 字段 | 类型 | 必须 | 说明 |
|------|------|:---:|------|
| `addr` | string | ✓ | 内存地址，16 进制，定宽 16 位 |
| `size` | int | ✓ | 访问字节数 |
| `val` | string | ✓ | 读取/写入的值，16 进制，定宽 16 位 |

```json
"mem_r": [
  {"addr": "0000000000462738", "size": 8, "val": "000000000046277A"}
]
```

---

## 完整示例

```json
{"addr":"00007FF730291133","bytes":"48 8B 4F 08","disasm":"mov rcx, qword ptr [rdi+0x8]","regs":{"RAX":"0000000000000032","RBX":"0000000000000002","RCX":"00000000FFFFFFFF","RDX":"00007FFD8AD90980","RSP":"000000000014FEC0","RBP":"0000000000000000","RDI":"0000000000462730","RSI":"0000000000000000","R8":"000000000014E2B8","R9":"00000000004667D2","R10":"0000000000000000","R11":"000000000014FDA0","R12":"0000000000000000","R13":"0000000000000000","R14":"0000000000000000","R15":"0000000000000000","EFLAGS":"0000000000000202"},"mem_r":[{"addr":"0000000000462738","size":8,"val":"000000000046277A"}],"mem_w":[],"thread_id":0,"branch_taken":null}
```

---

## 关键约束

1. **每行一个完整 JSON** — 不能有物理换行符 `\n` `\r` `\t` 嵌入字符串中（必须转义为 `\n` `\r` `\t` 两个字符）
2. **" 用 `\"` 转义，反斜杠用 `\\`**
3. **null / true / false 小写**，严格遵循 JSON 标准 (RFC 8259)
4. **所有地址和寄存器值** 16 进制、大写、定宽 16 位（即 `"0000000000000005"` 而非 `"5"` 或 `"0x5"`）
5. **空格分隔 hex 对** — `"48 8B"` 而非 `"488B"`
6. Pin pintool 每条指令后务必 `fflush(fp)`，避免进程崩溃丢失末尾数据

---

## Pin 代码片段参考

```cpp
VOID RecordInstruction(
    ADDRINT addr, CHAR* disasm, UINT32 insnSize,
    CONTEXT* ctx, THREADID tid,
    BOOL branchTaken, UINT32 memOpCount
) {
    // 读字节码
    UINT8 bytes[15];
    PIN_SafeCopy(bytes, (VOID*)addr, min(insnSize, 15));

    // 格式化 bytes
    char bytesHex[64] = {0};
    for (UINT32 i = 0; i < insnSize; i++)
        sprintf(bytesHex + i * 3, "%02X ", bytes[i]);

    // 读寄存器
    fprintf(trace_fp,
        "{\"addr\":\"%016llX\",\"bytes\":\"%s\",\"disasm\":\"%s\","
        "\"regs\":{"
        "\"RAX\":\"%016llX\",\"RBX\":\"%016llX\","
        // ... 其余寄存器 ...
        "\"EFLAGS\":\"%016llX\""
        "},"
        "\"mem_r\":[],\"mem_w\":[],"
        "\"thread_id\":%d,\"branch_taken\":%s}\n",
        addr, bytesHex, disasm,
        PIN_GetContextReg(ctx, REG_RAX),
        PIN_GetContextReg(ctx, REG_RBX),
        // ...
        PIN_GetContextReg(ctx, REG_EFLAGS),
        tid,
        branchTaken == 0 ? "null" : (branchTaken ? "true" : "false")
    );
    fflush(trace_fp);
}
```
