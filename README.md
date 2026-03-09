# Shimmy WASM Sandbox 🔒

Compile and execute untrusted code in WebAssembly sandbox. Perfect isolation without kernel features.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Why WASM?

| Feature | seccomp | LD_PRELOAD | **WASM** |
|---------|:-------:|:----------:|:--------:|
| No kernel features needed | ❌ | ✅ | ✅ |
| Lambda compatible | ❌ | ✅ | ✅ |
| Cannot bypass | ✅ | ❌ | ✅ |
| Performance | ~0ms | ~1ms | ~2x |
| Complexity | Low | Low | Medium |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     shimmy-wasm                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  User Code (.c/.rs/.go)                                     │
│       │                                                     │
│       ▼                                                     │
│  ┌─────────────┐                                           │
│  │ Compiler    │  clang --target=wasm32-wasi               │
│  │ (WASI SDK)  │  rustc --target wasm32-wasi               │
│  └─────────────┘                                           │
│       │                                                     │
│       ▼                                                     │
│  ┌─────────────┐                                           │
│  │ .wasm file  │  WebAssembly binary                       │
│  └─────────────┘                                           │
│       │                                                     │
│       ▼                                                     │
│  ┌─────────────┐                                           │
│  │ Runtime     │  wasmtime / wasmer / wasm3                │
│  │ (Sandbox)   │  --deny-network --deny-fs                 │
│  └─────────────┘                                           │
│       │                                                     │
│       ▼                                                     │
│  Isolated execution (no syscall access)                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Supported Languages

| Language | Compiler | Status |
|----------|----------|:------:|
| C/C++ | clang + WASI SDK | ✅ |
| Rust | rustc + wasm32-wasi | ✅ |
| Go | TinyGo | ✅ |
| AssemblyScript | asc | ✅ |
| Python | Pyodide | 🚧 |

## Quick Start

```bash
# Install runtime
curl https://wasmtime.dev/install.sh -sSf | bash

# Install WASI SDK
# macOS
brew install --cask wasi-sdk

# Linux
wget https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-20/wasi-sdk-20.0-linux.tar.gz
tar xf wasi-sdk-20.0-linux.tar.gz

# Compile and run
./shimmy-wasm compile examples/hello.c -o hello.wasm
./shimmy-wasm run hello.wasm --timeout 5
```

## Security Model

### What WASM Blocks (by design)

| Attack | Status | Reason |
|--------|:------:|--------|
| Network access | ✅ Blocked | No socket capability |
| File system | ✅ Blocked | No FS capability (unless granted) |
| Process spawn | ✅ Blocked | No process capability |
| Direct syscall | ✅ Blocked | WASM has no syscall instruction |
| Memory corruption | ✅ Blocked | Linear memory, bounds checked |
| Code injection | ✅ Blocked | Harvard architecture |

### What We Add

| Feature | Implementation |
|---------|----------------|
| CPU limit | wasmtime fuel metering |
| Memory limit | wasmtime memory limits |
| Timeout | External timeout + fuel |
| Output limit | Truncate stdout/stderr |
| Allowed paths | WASI preopens |

### Capability-Based Security

```bash
# No capabilities (maximum isolation)
shimmy-wasm run program.wasm

# Allow read /data directory
shimmy-wasm run program.wasm --dir /data:ro

# Allow write /tmp
shimmy-wasm run program.wasm --dir /tmp:rw

# Allow specific file
shimmy-wasm run program.wasm --file input.txt:ro
```

## API

### Python

```python
from shimmy_wasm import WasmSandbox

sandbox = WasmSandbox(
    timeout=5,
    memory_mb=128,
    fuel=1_000_000,
)

# Compile
wasm_bytes = sandbox.compile("hello.c", lang="c")

# Run
result = sandbox.run(wasm_bytes, stdin="input data")
print(result.stdout)
print(result.returncode)
```

### CLI

```bash
# Compile
shimmy-wasm compile hello.c -o hello.wasm
shimmy-wasm compile hello.rs -o hello.wasm --lang rust

# Run
shimmy-wasm run hello.wasm
shimmy-wasm run hello.wasm --timeout 5 --memory 128
shimmy-wasm run hello.wasm --stdin "input" --env KEY=VALUE

# Compile and run
shimmy-wasm exec hello.c --timeout 5
```

## Comparison with Other Approaches

| Approach | Security | Performance | Complexity | Lambda |
|----------|:--------:|:-----------:|:----------:|:------:|
| seccomp | 🟢🟢🟢 | 🟢🟢🟢 | 🟢🟢 | ❌ |
| LD_PRELOAD | 🟡 | 🟢🟢🟢 | 🟢🟢🟢 | ✅ |
| Language sandbox | 🟡 | 🟢🟢 | 🟢🟢 | ✅ |
| **WASM** | 🟢🟢🟢 | 🟢🟢 | 🟡 | ✅ |
| QEMU | 🟢🟢🟢 | 🔴 | 🔴 | ⚠️ |

## Limitations

1. **WASI compatibility** - Not all C libraries work with WASI
2. **Performance** - ~2x overhead compared to native
3. **Debugging** - Limited debugging support
4. **Dynamic linking** - Not well supported

## Runtimes

| Runtime | Language | Performance | Size |
|---------|----------|:-----------:|:----:|
| wasmtime | Rust | Fast | 20MB |
| wasmer | Rust | Fast | 25MB |
| wasm3 | C | Slower | 300KB |
| wasmi | Rust | Slower | 5MB |

**Recommended:** `wasmtime` for Lambda (good balance of speed and size)

## Project Structure

```
shimmy-wasm/
├── src/
│   ├── compiler.py     # Multi-language compiler
│   ├── runtime.py      # WASM runtime wrapper
│   ├── sandbox.py      # High-level sandbox API
│   └── cli.py          # Command line interface
├── runtimes/
│   └── wasmtime/       # Bundled wasmtime binary
├── examples/
│   ├── hello.c
│   ├── hello.rs
│   └── hello.go
├── tests/
│   └── test_sandbox.py
├── Dockerfile          # Lambda layer builder
└── README.md
```

## License

MIT License - see [LICENSE](LICENSE)

## Related Projects

- [Sandlock](https://github.com/bkmashiro/Sandlock) - Kernel-level sandbox
- [wasmtime](https://wasmtime.dev/) - Fast WASM runtime
- [WASI](https://wasi.dev/) - WebAssembly System Interface
