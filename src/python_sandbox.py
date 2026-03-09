#!/usr/bin/env python3
"""
Shimmy WASM Python Sandbox

Execute Python code inside WASM sandbox using pre-compiled Python interpreter.

Options:
1. Pyodide (CPython compiled to WASM) - Full Python, ~15MB
2. RustPython (Rust implementation) - Limited stdlib, ~5MB
3. MicroPython - Minimal Python, ~300KB
"""

import subprocess
import tempfile
import json
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any

# ============================================================
# Configuration
# ============================================================

@dataclass
class PythonSandboxConfig:
    """Python sandbox configuration."""
    timeout: int = 5
    memory_mb: int = 256  # Python needs more memory
    fuel: int = 10_000_000_000  # Python is slower, needs more fuel
    allow_imports: bool = False  # Allow importing modules
    allowed_modules: list = None  # Whitelist of allowed modules

# ============================================================
# Pyodide Support
# ============================================================

PYODIDE_RUNNER = '''
import sys
sys.path.insert(0, '/lib/python3.11')

# Sandbox restrictions
_blocked_modules = {blocked_modules}

class ImportBlocker:
    def find_module(self, name, path=None):
        if name.split('.')[0] in _blocked_modules:
            return self
        return None
    
    def load_module(self, name):
        raise ImportError(f"Module '{name}' is blocked")

if _blocked_modules:
    sys.meta_path.insert(0, ImportBlocker())

# User code
{user_code}
'''

def create_pyodide_package() -> Path:
    """
    Download and prepare Pyodide WASM package.
    Returns path to pyodide directory.
    """
    pyodide_dir = Path.home() / ".shimmy-wasm" / "pyodide"
    
    if pyodide_dir.exists():
        return pyodide_dir
    
    pyodide_dir.mkdir(parents=True, exist_ok=True)
    
    # Download Pyodide
    import urllib.request
    url = "https://cdn.jsdelivr.net/pyodide/v0.24.0/full/pyodide.tar.bz2"
    
    print(f"Downloading Pyodide (~15MB)...")
    # This would be done in production
    
    return pyodide_dir

# ============================================================
# RustPython Support (Simpler)
# ============================================================

RUSTPYTHON_WASM_URL = "https://github.com/AlysonNumberFIVE/rustpython_wasm/releases/download/v0.3.0/rustpython.wasm"

def get_rustpython() -> Path:
    """Download RustPython WASM if not present."""
    cache_dir = Path.home() / ".shimmy-wasm" / "runtimes"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    wasm_path = cache_dir / "rustpython.wasm"
    
    if not wasm_path.exists():
        print("Downloading RustPython WASM (~5MB)...")
        import urllib.request
        urllib.request.urlretrieve(RUSTPYTHON_WASM_URL, wasm_path)
    
    return wasm_path

# ============================================================
# MicroPython Support (Smallest)
# ============================================================

MICROPYTHON_WASM_URL = "https://micropython.org/resources/firmware/GENERIC_WASM-20231005-v1.21.0.wasm"

def get_micropython() -> Path:
    """Download MicroPython WASM if not present."""
    cache_dir = Path.home() / ".shimmy-wasm" / "runtimes"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    wasm_path = cache_dir / "micropython.wasm"
    
    if not wasm_path.exists():
        print("Downloading MicroPython WASM (~300KB)...")
        import urllib.request
        urllib.request.urlretrieve(MICROPYTHON_WASM_URL, wasm_path)
    
    return wasm_path

# ============================================================
# Main Sandbox
# ============================================================

@dataclass
class PythonResult:
    success: bool
    output: str
    error: Optional[str] = None

class PythonWasmSandbox:
    """Execute Python code in WASM sandbox."""
    
    def __init__(self, runtime: str = "micropython"):
        """
        Args:
            runtime: "micropython", "rustpython", or "pyodide"
        """
        self.runtime = runtime
        self._check_wasmtime()
    
    def _check_wasmtime(self):
        if not shutil.which("wasmtime"):
            raise RuntimeError("wasmtime not found")
    
    def run(self, code: str, config: Optional[PythonSandboxConfig] = None) -> PythonResult:
        """
        Execute Python code in WASM sandbox.
        
        Args:
            code: Python code to execute
            config: Sandbox configuration
            
        Returns:
            PythonResult with output or error
        """
        cfg = config or PythonSandboxConfig()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Write code to file
            code_file = tmpdir / "code.py"
            code_file.write_text(code)
            
            # Get runtime WASM
            if self.runtime == "micropython":
                wasm_path = get_micropython()
                cmd = self._build_micropython_cmd(wasm_path, code_file, cfg)
            elif self.runtime == "rustpython":
                wasm_path = get_rustpython()
                cmd = self._build_rustpython_cmd(wasm_path, code_file, cfg)
            else:
                raise ValueError(f"Unsupported runtime: {self.runtime}")
            
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=cfg.timeout + 5,
                )
                
                return PythonResult(
                    success=(result.returncode == 0),
                    output=result.stdout,
                    error=result.stderr if result.returncode != 0 else None,
                )
                
            except subprocess.TimeoutExpired:
                return PythonResult(
                    success=False,
                    output="",
                    error="Execution timed out",
                )
            except Exception as e:
                return PythonResult(
                    success=False,
                    output="",
                    error=str(e),
                )
    
    def _build_micropython_cmd(self, wasm: Path, code: Path, cfg: PythonSandboxConfig) -> list:
        """Build wasmtime command for MicroPython."""
        return [
            "wasmtime", "run",
            "--fuel", str(cfg.fuel),
            "--wasm-timeout", f"{cfg.timeout}s",
            f"--max-memory-size={cfg.memory_mb}M",
            "--dir", f"{code.parent}::ro",
            str(wasm),
            "--",
            str(code.name),
        ]
    
    def _build_rustpython_cmd(self, wasm: Path, code: Path, cfg: PythonSandboxConfig) -> list:
        """Build wasmtime command for RustPython."""
        return [
            "wasmtime", "run",
            "--fuel", str(cfg.fuel),
            "--wasm-timeout", f"{cfg.timeout}s",
            f"--max-memory-size={cfg.memory_mb}M",
            "--dir", f"{code.parent}::ro",
            str(wasm),
            str(code),
        ]

# ============================================================
# CLI
# ============================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Python WASM Sandbox")
    parser.add_argument("file", nargs="?", help="Python file to execute")
    parser.add_argument("-e", "--eval", help="Code string to execute")
    parser.add_argument("-r", "--runtime", choices=["micropython", "rustpython"], 
                        default="micropython", help="Python runtime")
    parser.add_argument("-t", "--timeout", type=int, default=5)
    parser.add_argument("-m", "--memory", type=int, default=256)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    # Get code
    if args.eval:
        code = args.eval
    elif args.file:
        code = Path(args.file).read_text()
    else:
        parser.print_help()
        return
    
    # Run
    sandbox = PythonWasmSandbox(runtime=args.runtime)
    config = PythonSandboxConfig(timeout=args.timeout, memory_mb=args.memory)
    result = sandbox.run(code, config)
    
    if args.json:
        print(json.dumps({
            "success": result.success,
            "output": result.output,
            "error": result.error,
        }))
    else:
        if result.output:
            print(result.output, end="")
        if result.error:
            print(f"Error: {result.error}", file=sys.stderr)
    
    exit(0 if result.success else 1)

if __name__ == "__main__":
    import sys
    main()
