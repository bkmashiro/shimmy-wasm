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

## Testing

```bash
# Install test dependencies
pip install pytest

# Run tests
python -m pytest tests/ -v

# Run specific test
python -m pytest tests/test_sandbox.py::TestSecurity -v
```

### Test Categories

| Category | Tests | Description |
|----------|:-----:|-------------|
| Compilation | 3 | C/C++ to WASM compilation |
| Execution | 3 | Basic execution, return codes |
| Security | 3 | Network, filesystem isolation |
| Resources | 3 | Timeout, fuel, memory limits |

## Benchmarks

```bash
python tests/benchmark.py
```

### Expected Results

| Benchmark | Native | WASM | Overhead |
|-----------|:------:|:----:|:--------:|
| Hello World | ~1ms | ~5ms | ~5x |
| Compute (100k sqrt) | ~3ms | ~6ms | ~2x |
| Fibonacci(35) | ~50ms | ~80ms | ~1.6x |
| Memory (1MB) | ~2ms | ~5ms | ~2.5x |

**Conclusion:** WASM overhead is ~1.5-3x for CPU-bound tasks, acceptable for sandboxing.

## WASI Capabilities

Full control over sandbox capabilities with safety annotations.

### Safety Levels

| Level | Meaning |
|:-----:|---------|
| 🟢 | Safe - No security impact |
| 🟡 | Caution - Limited risk, usually safe |
| 🟠 | Warning - Potential information leak |
| 🔴 | Dangerous - Can cause side effects |
| ❌ | Blocked - Not possible in WASI |

### Complete Configuration

```python
config = SandboxConfig(
    # ====== Resource Limits (🟢 Safe) ======
    timeout=5,                  # Wall clock timeout (seconds)
    memory_mb=128,              # Memory limit
    fuel=1_000_000_000,         # Instruction limit (CPU)
    max_output=1024*1024,       # Max stdout/stderr (1MB)
    
    # ====== Filesystem (🟡/🔴) ======
    allow_fs_read=False,        # 🟡 Read allowed paths
    allow_fs_write=False,       # 🔴 Write (safe if ephemeral=True)
    allowed_dirs=["/data:ro"],  # Preopened directories
    allowed_files=[],           # Preopened files
    
    # ====== Environment (🟠) ======
    allow_env=False,            # 🟠 Pass env vars to sandbox
    env={"KEY": "value"},       # Env vars to pass
    allow_args=True,            # 🟡 Program sees arguments
    args=["arg1", "arg2"],      # Arguments to pass
    
    # ====== Time & Random (🟢) ======
    allow_clock=True,           # 🟢 Wall clock access
    allow_monotonic_clock=True, # 🟡 Monotonic clock (timing)
    allow_random=True,          # 🟢 Random numbers
    
    # ====== Standard I/O (🟢/🟡) ======
    stdin="input data",         # 🟢 Input data
    inherit_stdout=True,        # 🟢 Capture stdout
    inherit_stderr=True,        # 🟢 Capture stderr
    inherit_stdin=False,        # 🟡 Host stdin (caution)
    
    # ====== Network (🔴 Experimental) ======
    allow_tcp_listen=False,     # 🔴 Listen on ports
    allow_tcp_connect=False,    # 🔴 Outbound connections
    allow_udp=False,            # 🔴 UDP sockets
    tcp_listen_ports=[8080],    # Allowed ports
    
    # ====== Advanced (🟡/🟠) ======
    allow_threads=False,        # 🟡 WASM threads
    max_threads=4,              # Max thread count
    allow_shared_memory=False,  # 🟠 Shared memory
    allow_simd=True,            # 🟡 SIMD instructions
    enable_debug=False,         # 🟠 Debug info
    
    # ====== Ephemeral Mode (🟢) ======
    ephemeral=True,             # 🟢 No side effects
    collect_output_files=False, # 🟢 Get files from /tmp
    output_dir=None,            # Where to save output
)
```

### Capability Matrix

| Capability | Default | Safety | Side Effects |
|------------|:-------:|:------:|:------------:|
| Filesystem Read | ❌ | 🟡 | None |
| Filesystem Write | ❌ | 🔴 | ⚠️ If ephemeral=False |
| Environment | ❌ | 🟠 | None |
| Clock | ✅ | 🟢 | None |
| Random | ✅ | 🟢 | None |
| TCP Listen | ❌ | 🔴 | Network exposure |
| TCP Connect | ❌ | 🔴 | Data exfiltration |
| Threads | ❌ | 🟡 | None |
| SIMD | ✅ | 🟡 | Side-channel risk |
| **Process Spawn** | ❌ | ❌ | **Not possible** |
| **Signals** | ❌ | ❌ | **Not possible** |
| **Raw Syscalls** | ❌ | ❌ | **Not possible** |

### ⚠️ Dangerous Combinations

```python
# 🔴 DANGEROUS: Can modify host files!
config = SandboxConfig(
    allow_fs_write=True,
    ephemeral=False,  # Writes persist!
    allowed_dirs=["/important/data"],
)

# 🔴 DANGEROUS: Data exfiltration possible!
config = SandboxConfig(
    allow_tcp_connect=True,  # Can send data out
)

# 🟢 SAFE: Even with writes enabled
config = SandboxConfig(
    allow_fs_write=True,
    ephemeral=True,  # All writes discarded
)
```

## Threading

### Status: Not Implemented (Possible but Unnecessary)

WASM supports threads via `wasm32-wasi-threads` target, but we intentionally don't implement it:

| Reason | Explanation |
|--------|-------------|
| **Security** | SharedArrayBuffer + timing = Spectre risk |
| **Complexity** | Adds attack surface |
| **Use Case** | Sandbox execution rarely needs parallelism |

If threading becomes necessary in the future:

```python
# Would require these config options (not implemented):
# allow_threads: bool = False
# max_threads: int = 4
# allow_shared_memory: bool = False

# Compiler: clang --target=wasm32-wasi-threads -pthread
# Runtime: wasmtime --wasm-threads=y --max-threads=4
```

## Python Support

Execute Python code in WASM sandbox:

```python
from src import PythonWasmSandbox

sandbox = PythonWasmSandbox(runtime='micropython')
result = sandbox.run('print(sum(range(100)))')
print(result.output)  # "4950"
```

### Supported Runtimes

| Runtime | Size | Features | Speed |
|---------|:----:|----------|:-----:|
| MicroPython | 300KB | Basic | Fast |
| RustPython | 5MB | More stdlib | Medium |
| Pyodide | 15MB | Full CPython | Slow |

## Project Structure

```
shimmy-wasm/
├── src/
│   ├── __init__.py
│   ├── sandbox.py          # Main sandbox API
│   └── python_sandbox.py   # Python WASM support
├── examples/
│   ├── hello.c
│   ├── hello.rs
│   ├── hello.py
│   └── compute.c
├── tests/
│   ├── test_sandbox.py     # Unit tests
│   └── benchmark.py        # Performance benchmarks
├── shimmy-wasm             # CLI entry point
├── setup.py
└── README.md
```

## License

MIT License - see [LICENSE](LICENSE)

## Related Projects

- [Sandlock](https://github.com/bkmashiro/Sandlock) - Kernel-level sandbox
- [wasmtime](https://wasmtime.dev/) - Fast WASM runtime
- [WASI](https://wasi.dev/) - WebAssembly System Interface
