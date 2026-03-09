# Shimmy WASM - Technical Report

## Overview

Shimmy WASM is a WebAssembly-based sandbox for executing untrusted code securely. It compiles source code to WASM and executes it in a capability-controlled environment using wasmtime.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        User Code                              │
│                    (C, C++, Rust, Go)                        │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                    WASM Compiler                              │
│          (clang --target=wasm32-wasi / rustc)                │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                     WASM Binary                               │
│           (Portable, sandboxed bytecode)                     │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                    WASI Runtime                               │
│                     (wasmtime)                                │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                    Capabilities                         │  │
│  │  • Filesystem (preopened only)                         │  │
│  │  • Environment (filtered)                               │  │
│  │  • Clock/Random (optional)                              │  │
│  │  • Network (experimental, usually off)                  │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                  Resource Limits                        │  │
│  │  • Memory (--max-memory-size)                          │  │
│  │  • CPU (--fuel)                                         │  │
│  │  • Time (--wasm-timeout)                                │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                     Host System                               │
│        (Only sees preopened paths, nothing else)             │
└──────────────────────────────────────────────────────────────┘
```

## Security Model

### Why WASM is Fundamentally Secure

| Property | Native Code | WASM |
|----------|:-----------:|:----:|
| Direct syscalls | ✅ Possible | ❌ Impossible |
| Memory corruption | ✅ Exploitable | ❌ Trapped |
| ROP/JOP attacks | ✅ Possible | ❌ Impossible |
| Type confusion | ✅ Possible | ❌ Type-safe |
| Buffer overflow | ✅ Dangerous | ❌ Bounds-checked |

### WASM vs Other Sandboxing Approaches

| Approach | Isolation Level | Performance | Escape Difficulty |
|----------|:---------------:|:-----------:|:-----------------:|
| **WASM** | Process/Memory | ~2x | Requires wasmtime bug |
| seccomp | Syscall | ~1.01x | Allowed syscall abuse |
| Docker | Container | ~1.05x | Kernel exploit |
| VM | Hardware | ~1.2x | Hypervisor exploit |
| LD_PRELOAD | Library | ~1.0x | Direct syscall/static |

### Attack Surface Analysis

| Attack Vector | Status | Reason |
|---------------|:------:|--------|
| Direct syscall | ❌ Blocked | No syscall instruction in WASM |
| Fork bomb | ❌ Blocked | No fork/exec in WASI |
| Network exfiltration | ❌ Blocked | No socket API |
| File system escape | ❌ Blocked | Only preopened paths |
| Memory corruption | ❌ Blocked | Linear memory bounds checked |
| Timing side-channel | ⚠️ Limited | Clock can be disabled |
| Spectre | ⚠️ Limited | Single-threaded, no SharedArrayBuffer |

## Performance Benchmarks

### Methodology

- **Native**: GCC -O2 compiled binaries
- **WASM Compile**: Time to compile source to .wasm
- **WASM Run**: Time to execute pre-compiled .wasm
- **WASM Full**: Compile + Execute (typical sandbox use)

### Results (Expected)

| Benchmark | Native | WASM Run | WASM Full | Overhead (Run) |
|-----------|:------:|:--------:|:---------:|:--------------:|
| Hello World | 1 ms | 4-6 ms | 50-100 ms | 4-6x |
| Compute (100k ops) | 3 ms | 5-8 ms | 60-110 ms | 1.7-2.7x |
| Fibonacci(35) | 50 ms | 70-100 ms | 120-200 ms | 1.4-2x |
| Memory (1MB alloc) | 2 ms | 4-6 ms | 50-100 ms | 2-3x |
| String processing | 10 ms | 15-25 ms | 70-130 ms | 1.5-2.5x |

### Analysis

1. **Startup Cost**: WASM has ~50-100ms compilation overhead
   - Mitigation: Cache compiled WASM modules
   - Mitigation: Use ahead-of-time compilation

2. **Runtime Overhead**: ~1.5-3x for CPU-bound tasks
   - Acceptable for sandboxing use case
   - Can be reduced with optimization flags

3. **Memory Overhead**: Minimal (~10MB for wasmtime runtime)

### Comparison with Alternatives

| Solution | Startup | Runtime Overhead | Security |
|----------|:-------:|:----------------:|:--------:|
| WASM (wasmtime) | ~50ms | ~2x | ⭐⭐⭐⭐⭐ |
| Docker | ~500ms | ~1.05x | ⭐⭐⭐ |
| gVisor | ~200ms | ~1.5x | ⭐⭐⭐⭐ |
| Firecracker | ~125ms | ~1.1x | ⭐⭐⭐⭐⭐ |
| QEMU user | ~100ms | ~5x | ⭐⭐⭐⭐ |

**Conclusion**: WASM offers the best security/performance tradeoff for sandboxing untrusted code snippets.

## WASI Capabilities

### Complete Capability Reference

#### Safe (🟢)

| Capability | Flag | Description |
|------------|------|-------------|
| Timeout | `timeout` | Wall-clock execution limit |
| Memory Limit | `memory_mb` | Maximum linear memory |
| CPU Limit | `fuel` | Instruction count limit |
| Output Limit | `max_output` | Stdout/stderr truncation |
| Clock | `allow_clock` | Time queries (usually safe) |
| Random | `allow_random` | Cryptographic RNG |
| Stdout/Stderr | `inherit_stdout/stderr` | Capture output |

#### Caution (🟡)

| Capability | Flag | Description |
|------------|------|-------------|
| Filesystem Read | `allow_fs_read` | Read preopened paths only |
| Arguments | `allow_args` | Program sees argv |
| Monotonic Clock | `allow_monotonic_clock` | High-precision timing |
| SIMD | `allow_simd` | Vector instructions |

#### Warning (🟠)

| Capability | Flag | Description |
|------------|------|-------------|
| Environment | `allow_env` | Pass env vars (filtered) |
| Debug | `enable_debug` | Debug info exposure |
| Inherit Stdin | `inherit_stdin` | Host stdin passthrough |

#### Dangerous (🔴)

| Capability | Flag | Side Effects |
|------------|------|--------------|
| Filesystem Write | `allow_fs_write` | ⚠️ Only if `ephemeral=False` |
| TCP Listen | `allow_tcp_listen` | Network exposure |
| TCP Connect | `allow_tcp_connect` | Data exfiltration |
| UDP | `allow_udp` | Network access |

#### Impossible (❌)

| Capability | Reason |
|------------|--------|
| Process spawn | Not in WASI spec |
| Signal handling | Not in WASI spec |
| Raw syscalls | No syscall instruction |
| Shared memory | Disabled by default |
| Host memory access | Linear memory isolated |

## Ephemeral Mode

### How It Works

```
Ephemeral Mode ON (default):
┌────────────────────────────────────────────┐
│ 1. Create temp directory                    │
│    /var/folders/.../shimmy_wasm_xxx/       │
│                                             │
│ 2. Create isolated /tmp                     │
│    shimmy_wasm_xxx/sandbox_tmp/             │
│                                             │
│ 3. Copy allowed directories (if writable)  │
│    /data → shimmy_wasm_xxx/copy_data/      │
│                                             │
│ 4. Run WASM with mapped paths              │
│    WASM /tmp  → sandbox_tmp                │
│    WASM /data → copy_data                  │
│                                             │
│ 5. Collect output files (optional)         │
│    sandbox_tmp/* → result.output_files     │
│                                             │
│ 6. Delete temp directory                    │
│    ALL CHANGES DISCARDED                   │
└────────────────────────────────────────────┘
```

### Guarantees

| Guarantee | Ephemeral ON | Ephemeral OFF |
|-----------|:------------:|:-------------:|
| Host /tmp untouched | ✅ | ✅ |
| Allowed dirs untouched | ✅ | ❌ |
| No persistent files | ✅ | ❌ |
| Output file collection | ✅ | ❌ |

## Threading

### Status: Not Implemented

WASM threads are technically possible but intentionally not implemented.

#### Why Not Implemented

1. **Security**: SharedArrayBuffer + high-precision timing = Spectre
2. **Complexity**: Adds attack surface without clear benefit
3. **Use Case**: Untrusted code execution rarely needs parallelism

#### If Needed in Future

```python
# Would require:
config = SandboxConfig(
    allow_threads=True,
    max_threads=4,
    allow_shared_memory=True,  # Required for threads
)

# Compiler flags:
# clang --target=wasm32-wasi-threads -pthread ...

# Runtime flags:
# wasmtime --wasm-threads=y --max-threads=4 ...
```

## Lambda Deployment

### Recommended Configuration

```python
config = SandboxConfig(
    # Tight resource limits
    timeout=5,
    memory_mb=128,
    fuel=1_000_000_000,
    max_output=65536,
    
    # Maximum isolation
    allow_fs_read=False,
    allow_fs_write=False,
    allow_env=False,
    allow_tcp_connect=False,
    
    # Safe defaults
    allow_clock=True,
    allow_random=True,
    
    # Always ephemeral
    ephemeral=True,
)
```

### Lambda Layer Size

| Component | Size |
|-----------|:----:|
| wasmtime binary | ~15 MB |
| WASI SDK (optional) | ~50 MB |
| Python runtime | ~5 MB |
| **Total Layer** | **~20-70 MB** |

### Performance in Lambda

| Operation | Cold Start | Warm |
|-----------|:----------:|:----:|
| WASM compile | 100-500ms | 50-100ms |
| WASM execute | 10-100ms | 10-100ms |
| Total | 110-600ms | 60-200ms |

## Test Coverage

### Test Categories

| Category | Tests | Coverage |
|----------|:-----:|:--------:|
| Compilation | 3 | Basic |
| Execution | 3 | Basic |
| Security | 15 | Comprehensive |
| Ephemeral | 8 | Comprehensive |
| Resource Limits | 4 | Basic |
| **Total** | **33** | - |

### Security Test Matrix

| Attack | Test | Status |
|--------|------|:------:|
| Network (TCP) | `test_no_tcp_socket` | ✅ |
| Network (UDP) | `test_no_udp_socket` | ✅ |
| Network (DNS) | `test_no_dns_resolution` | ✅ |
| FS (root) | `test_no_root_access` | ✅ |
| FS (/etc) | `test_no_etc_passwd` | ✅ |
| FS (/proc) | `test_no_proc` | ✅ |
| FS (escape) | `test_cannot_escape_sandbox` | ✅ |
| Process (fork) | `test_no_fork` | ✅ |
| Process (exec) | `test_no_exec` | ✅ |
| Process (system) | `test_no_system` | ✅ |
| Memory (limit) | `test_memory_limit_enforced` | ✅ |
| Memory (overflow) | `test_buffer_overflow_trapped` | ✅ |
| Memory (null) | `test_null_pointer_trapped` | ✅ |
| Env (leak) | `test_no_host_env_by_default` | ✅ |
| Env (filter) | `test_only_allowed_env` | ✅ |

## Comparison with Sandlock

| Feature | Shimmy WASM | Sandlock |
|---------|:-----------:|:--------:|
| Target | Any platform | Linux only |
| Mechanism | WASM compilation | seccomp/Landlock |
| Performance | ~2x overhead | ~1.01x overhead |
| Security | Design-level | Syscall filtering |
| Language support | C/C++/Rust/Go | Any executable |
| Lambda compatible | ✅ | ⚠️ Limited |
| Escape difficulty | wasmtime bug | Allowed syscall |

### When to Use Each

| Use Case | Recommendation |
|----------|----------------|
| Lambda execution | **Shimmy WASM** |
| Maximum security | **Shimmy WASM** |
| Performance critical | Sandlock |
| Python/Node scripts | Both |
| Pre-compiled binaries | Sandlock |
| Cross-platform | **Shimmy WASM** |

## Future Work

1. **WASM Module Caching**: Cache compiled modules for faster warm starts
2. **AOT Compilation**: Pre-compile to native for better performance
3. **Python WASM**: MicroPython/RustPython integration for Lambda
4. **Streaming Compilation**: Start execution before compilation finishes
5. **Memory Snapshots**: Fast restore from saved state

## Conclusion

Shimmy WASM provides a fundamentally secure sandbox for executing untrusted code. By compiling to WebAssembly, we achieve:

1. **Design-level security**: No syscall instruction exists in WASM
2. **Memory safety**: All accesses bounds-checked
3. **Capability control**: Fine-grained permission system
4. **Portability**: Works anywhere wasmtime runs
5. **Acceptable performance**: ~2x overhead is reasonable for security

The tradeoff is compilation overhead (~50-100ms), which is acceptable for our use case of sandboxing code snippets in a serverless environment.
