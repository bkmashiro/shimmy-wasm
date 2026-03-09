#!/usr/bin/env python3
"""
Shimmy WASM Sandbox Benchmarks

Compare WASM sandbox performance with native execution.

Run: python tests/benchmark.py
"""

import subprocess
import tempfile
import time
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.sandbox import WasmSandbox, SandboxConfig, Language

# ============================================================
# Benchmark Code
# ============================================================

HELLO_C = '''
#include <stdio.h>
int main() {
    printf("Hello\\n");
    return 0;
}
'''

COMPUTE_C = '''
#include <stdio.h>
#include <math.h>

int main() {
    double sum = 0;
    for (int i = 1; i <= 100000; i++) {
        sum += sqrt((double)i);
    }
    printf("%.2f\\n", sum);
    return 0;
}
'''

FIBONACCI_C = '''
#include <stdio.h>

long fib(int n) {
    if (n <= 1) return n;
    return fib(n-1) + fib(n-2);
}

int main() {
    printf("%ld\\n", fib(35));
    return 0;
}
'''

MEMORY_C = '''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main() {
    char* buf = malloc(1024 * 1024);  // 1MB
    memset(buf, 'A', 1024 * 1024);
    long sum = 0;
    for (int i = 0; i < 1024 * 1024; i++) {
        sum += buf[i];
    }
    printf("%ld\\n", sum);
    free(buf);
    return 0;
}
'''

# ============================================================
# Benchmark Runner
# ============================================================

def benchmark_native(code: str, runs: int = 5) -> float:
    """Benchmark native execution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "code.c"
        bin = Path(tmpdir) / "code"
        
        src.write_text(code)
        
        # Compile
        subprocess.run(["gcc", "-O2", "-o", str(bin), str(src), "-lm"], 
                      capture_output=True, check=True)
        
        # Run multiple times
        times = []
        for _ in range(runs):
            start = time.perf_counter()
            subprocess.run([str(bin)], capture_output=True)
            times.append((time.perf_counter() - start) * 1000)
        
        return sum(times) / len(times)

def benchmark_wasm(sandbox: WasmSandbox, code: str, runs: int = 5) -> float:
    """Benchmark WASM execution."""
    # Compile once
    wasm = sandbox.compile(code, Language.C)
    
    # Run multiple times
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        sandbox.run(wasm)
        times.append((time.perf_counter() - start) * 1000)
    
    return sum(times) / len(times)

def benchmark_wasm_full(sandbox: WasmSandbox, code: str, runs: int = 5) -> float:
    """Benchmark WASM compile + execute."""
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        sandbox.exec(code, Language.C)
        times.append((time.perf_counter() - start) * 1000)
    
    return sum(times) / len(times)

# ============================================================
# Main
# ============================================================

def main():
    print("=" * 60)
    print("Shimmy WASM Sandbox Benchmarks")
    print("=" * 60)
    print()
    
    sandbox = WasmSandbox()
    
    benchmarks = [
        ("Hello World", HELLO_C),
        ("Compute (100k sqrt)", COMPUTE_C),
        ("Fibonacci(35)", FIBONACCI_C),
        ("Memory (1MB)", MEMORY_C),
    ]
    
    results = []
    
    print(f"{'Benchmark':<25} {'Native':<12} {'WASM Run':<12} {'WASM Full':<12} {'Overhead':<10}")
    print("-" * 75)
    
    for name, code in benchmarks:
        try:
            native_ms = benchmark_native(code, runs=3)
        except Exception as e:
            native_ms = None
            
        try:
            wasm_run_ms = benchmark_wasm(sandbox, code, runs=3)
        except Exception as e:
            wasm_run_ms = None
            
        try:
            wasm_full_ms = benchmark_wasm_full(sandbox, code, runs=3)
        except Exception as e:
            wasm_full_ms = None
        
        overhead = ""
        if native_ms and wasm_run_ms:
            overhead = f"{wasm_run_ms / native_ms:.1f}x"
        
        native_str = f"{native_ms:.1f}ms" if native_ms else "N/A"
        wasm_run_str = f"{wasm_run_ms:.1f}ms" if wasm_run_ms else "N/A"
        wasm_full_str = f"{wasm_full_ms:.1f}ms" if wasm_full_ms else "N/A"
        
        print(f"{name:<25} {native_str:<12} {wasm_run_str:<12} {wasm_full_str:<12} {overhead:<10}")
        
        results.append({
            "name": name,
            "native_ms": native_ms,
            "wasm_run_ms": wasm_run_ms,
            "wasm_full_ms": wasm_full_ms,
            "overhead": wasm_run_ms / native_ms if native_ms and wasm_run_ms else None,
        })
    
    print()
    print("=" * 60)
    print("Notes:")
    print("- Native: gcc -O2 compiled binary")
    print("- WASM Run: Pre-compiled WASM execution only")
    print("- WASM Full: Compile + Execute")
    print("- Overhead: WASM Run / Native time")
    print("=" * 60)
    
    # Save results
    with open("benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nResults saved to benchmark_results.json")

if __name__ == "__main__":
    main()
