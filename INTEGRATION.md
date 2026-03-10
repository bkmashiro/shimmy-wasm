# Shimmy Integration Guide

How to integrate `shimmy-wasm` (Python WASM sandbox) with the Shimmy Go service.

## Architecture Options

### Option 1: Subprocess (Recommended for simplicity)

Call `shimmy-wasm` CLI from Go using `os/exec`:

```go
package sandbox

import (
    "encoding/json"
    "os/exec"
    "time"
)

type Result struct {
    Success    bool   `json:"success"`
    ReturnCode int    `json:"returncode"`
    Stdout     string `json:"stdout"`
    Stderr     string `json:"stderr"`
    Error      string `json:"error"`
}

func ExecCode(source, lang string, timeout time.Duration) (*Result, error) {
    cmd := exec.Command("shimmy-wasm", "exec", source,
        "--lang", lang,
        "--timeout", fmt.Sprintf("%d", int(timeout.Seconds())),
        "--json",
    )
    out, err := cmd.Output()
    if err != nil {
        // shimmy-wasm returns non-zero on sandbox failure, parse JSON anyway
        if exitErr, ok := err.(*exec.ExitError); ok {
            out = exitErr.Stderr
        }
    }
    var result Result
    json.Unmarshal(out, &result)
    return &result, nil
}
```

**Pros:** Simple, language boundary is clean, Python handles WASI SDK details.
**Cons:** Process spawn overhead (~10-30ms per call), serialization cost.

### Option 2: HTTP Server

Run `shimmy-wasm` as a long-lived HTTP service:

```python
# server.py
from flask import Flask, request, jsonify
from src.sandbox import WasmSandbox, SandboxConfig, Language

app = Flask(__name__)
sandbox = WasmSandbox()

@app.route("/exec", methods=["POST"])
def exec_code():
    data = request.json
    config = SandboxConfig(
        timeout=data.get("timeout", 5),
        memory_mb=data.get("memory_mb", 128),
        stdin=data.get("stdin"),
    )
    result = sandbox.exec(data["source"], Language(data["language"]), config)
    return jsonify({
        "success": result.success,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.returncode,
        "time_ms": result.time_ms,
    })
```

```go
// Go client
func ExecViaHTTP(source, lang string) (*Result, error) {
    body, _ := json.Marshal(map[string]any{
        "source":   source,
        "language": lang,
        "timeout":  5,
    })
    resp, err := http.Post("http://localhost:8080/exec", "application/json",
        bytes.NewReader(body))
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()
    var result Result
    json.NewDecoder(resp.Body).Decode(&result)
    return &result, nil
}
```

**Pros:** Amortizes Python startup, supports concurrency, easy to scale.
**Cons:** Extra service to deploy/monitor, network overhead.

### Option 3: Go Direct wasmtime (No Python)

Use [wasmtime-go](https://github.com/bytecodealliance/wasmtime-go) directly:

```go
import "github.com/bytecodealliance/wasmtime-go"

func RunWASM(wasmBytes []byte) (string, error) {
    engine := wasmtime.NewEngine()
    module, _ := wasmtime.NewModule(engine, wasmBytes)
    store := wasmtime.NewStore(engine)
    // ... configure WASI, instantiate, call _start
}
```

**Pros:** No Python dependency, lowest latency, single binary.
**Cons:** Must reimplement compilation pipeline and WASI config in Go.

## Performance Comparison

| Approach | Latency (hello world) | Throughput | Complexity |
|---|---|---|---|
| Subprocess | ~50-100ms | Low (serial) | Low |
| HTTP Server | ~20-50ms | Medium (concurrent) | Medium |
| Go wasmtime-go | ~5-15ms | High | High |

### Key Factors

- **Compilation dominates:** Compiling C→WASM (~50-100ms) dwarfs the execution time (~1-5ms). All approaches pay this cost unless WASM binaries are cached.
- **Python overhead:** Python process startup adds ~30ms for subprocess. HTTP amortizes this.
- **Go native:** Eliminates Python entirely. Best for high-throughput. But you need to handle WASI SDK toolchain yourself.

### Recommendation

| Use Case | Recommended Approach |
|---|---|
| Prototype / low traffic | Subprocess |
| Production with moderate load | HTTP Server |
| High-throughput / Lambda | Go wasmtime-go |
| Need Python-specific sandboxing | HTTP Server (use PythonWasmSandbox) |

## WASM Binary Caching

For all approaches, cache compiled WASM binaries to skip recompilation:

```python
# Python side
import hashlib

def compile_cached(source: str, lang: Language) -> bytes:
    key = hashlib.sha256(source.encode()).hexdigest()
    cache_path = Path(f".cache/wasm/{key}.wasm")
    if cache_path.exists():
        return cache_path.read_bytes()
    wasm = sandbox.compile(source, lang)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(wasm)
    return wasm
```

This reduces repeat-execution latency from ~100ms to ~5ms.

## Security Notes

- The WASM sandbox provides memory isolation, no filesystem access by default, and no network access.
- When using subprocess or HTTP, the Go service trusts the Python sandbox to enforce isolation.
- For defense in depth, also run the Python service in a container with restricted syscalls.
- Never pass unsanitized user input as command-line arguments to `shimmy-wasm` — use `--json` mode or the HTTP API.
