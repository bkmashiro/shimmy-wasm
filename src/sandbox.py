#!/usr/bin/env python3
"""
Shimmy WASM Sandbox

High-level API for compiling and executing code in WASM sandbox.
"""

import subprocess
import tempfile
import shutil
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum

class Language(Enum):
    C = "c"
    CPP = "cpp"
    RUST = "rust"
    GO = "go"
    ASSEMBLYSCRIPT = "assemblyscript"

@dataclass
class SandboxConfig:
    """Sandbox configuration."""
    # Resource limits
    timeout: int = 5                    # Seconds
    memory_mb: int = 128                # Memory limit
    fuel: int = 1_000_000_000           # Instruction limit (wasmtime fuel)
    max_output: int = 1024 * 1024       # 1MB output limit
    
    # WASI capabilities (all False = maximum isolation)
    allow_fs_read: bool = False         # Allow filesystem reads
    allow_fs_write: bool = False        # Allow filesystem writes
    allow_env: bool = False             # Allow environment access
    allow_clock: bool = True            # Allow clock access (usually harmless)
    allow_random: bool = True           # Allow random number generation
    
    # Preopened paths (only effective if allow_fs_* is True)
    allowed_dirs: List[str] = field(default_factory=list)  # Preopened directories
    allowed_files: List[str] = field(default_factory=list) # Preopened files
    
    # Environment (only effective if allow_env is True)
    env: Dict[str, str] = field(default_factory=dict)
    
    # Input
    stdin: Optional[str] = None
    
    # Ephemeral mode: no side effects after execution
    # All filesystem writes go to temp copies, discarded after run
    ephemeral: bool = True              # Default: no side effects
    
    # Output collection (only in ephemeral mode)
    collect_output_files: bool = False  # Collect files written to /tmp
    output_dir: Optional[str] = None    # Where to copy output files

@dataclass 
class ExecutionResult:
    """Result of sandbox execution."""
    success: bool
    returncode: int
    stdout: str
    stderr: str
    error: Optional[str] = None
    fuel_consumed: int = 0
    time_ms: int = 0
    output_files: Dict[str, bytes] = field(default_factory=dict)  # Files from /tmp

class CompilerError(Exception):
    """Raised when compilation fails."""
    pass

class RuntimeError(Exception):
    """Raised when WASM execution fails."""
    pass

class WasmSandbox:
    """WASM-based sandbox for executing untrusted code."""
    
    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check if required tools are installed."""
        # Check wasmtime
        if not shutil.which("wasmtime"):
            raise RuntimeError("wasmtime not found. Install: curl https://wasmtime.dev/install.sh -sSf | bash")
    
    def _detect_language(self, source_path: Path) -> Language:
        """Detect language from file extension."""
        ext_map = {
            '.c': Language.C,
            '.h': Language.C,
            '.cpp': Language.CPP,
            '.cc': Language.CPP,
            '.cxx': Language.CPP,
            '.rs': Language.RUST,
            '.go': Language.GO,
            '.ts': Language.ASSEMBLYSCRIPT,
        }
        ext = source_path.suffix.lower()
        if ext not in ext_map:
            raise CompilerError(f"Unknown file extension: {ext}")
        return ext_map[ext]
    
    def compile(self, source: str, lang: Optional[Language] = None, 
                output: Optional[Path] = None) -> bytes:
        """
        Compile source code to WASM.
        
        Args:
            source: Source code string or file path
            lang: Programming language (auto-detected if not specified)
            output: Output path for .wasm file
            
        Returns:
            WASM binary bytes
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Determine if source is a file path or code string
            if Path(source).exists():
                source_path = Path(source)
                if lang is None:
                    lang = self._detect_language(source_path)
                source_code = source_path.read_text()
            else:
                source_code = source
                if lang is None:
                    lang = Language.C  # Default to C
                source_path = tmpdir / f"source.{lang.value}"
                source_path.write_text(source_code)
            
            # Output path
            wasm_path = output or (tmpdir / "output.wasm")
            
            # Compile based on language
            if lang == Language.C:
                self._compile_c(source_path, wasm_path)
            elif lang == Language.CPP:
                self._compile_cpp(source_path, wasm_path)
            elif lang == Language.RUST:
                self._compile_rust(source_path, wasm_path)
            elif lang == Language.GO:
                self._compile_go(source_path, wasm_path)
            else:
                raise CompilerError(f"Unsupported language: {lang}")
            
            return wasm_path.read_bytes()
    
    def _compile_c(self, source: Path, output: Path):
        """Compile C to WASM using clang + WASI SDK."""
        # Try to find WASI SDK
        wasi_sdk = self._find_wasi_sdk()
        
        if wasi_sdk:
            clang = wasi_sdk / "bin" / "clang"
            sysroot = wasi_sdk / "share" / "wasi-sysroot"
            cmd = [
                str(clang),
                f"--sysroot={sysroot}",
                "-O2",
                "-o", str(output),
                str(source),
            ]
        else:
            # Try system clang with wasm target
            cmd = [
                "clang",
                "--target=wasm32-wasi",
                "-O2",
                "-o", str(output),
                str(source),
            ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise CompilerError(f"C compilation failed:\n{result.stderr}")
    
    def _compile_cpp(self, source: Path, output: Path):
        """Compile C++ to WASM."""
        wasi_sdk = self._find_wasi_sdk()
        
        if wasi_sdk:
            clangpp = wasi_sdk / "bin" / "clang++"
            sysroot = wasi_sdk / "share" / "wasi-sysroot"
            cmd = [
                str(clangpp),
                f"--sysroot={sysroot}",
                "-O2",
                "-o", str(output),
                str(source),
            ]
        else:
            cmd = [
                "clang++",
                "--target=wasm32-wasi",
                "-O2",
                "-o", str(output),
                str(source),
            ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise CompilerError(f"C++ compilation failed:\n{result.stderr}")
    
    def _compile_rust(self, source: Path, output: Path):
        """Compile Rust to WASM."""
        cmd = [
            "rustc",
            "--target", "wasm32-wasi",
            "-O",
            "-o", str(output),
            str(source),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise CompilerError(f"Rust compilation failed:\n{result.stderr}")
    
    def _compile_go(self, source: Path, output: Path):
        """Compile Go to WASM using TinyGo."""
        cmd = [
            "tinygo", "build",
            "-target", "wasi",
            "-o", str(output),
            str(source),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise CompilerError(f"Go compilation failed:\n{result.stderr}")
    
    def _find_wasi_sdk(self) -> Optional[Path]:
        """Find WASI SDK installation."""
        # Common locations
        locations = [
            Path("/opt/wasi-sdk"),
            Path.home() / ".wasi-sdk",
            Path("/usr/local/wasi-sdk"),
            # macOS Homebrew
            Path("/opt/homebrew/opt/wasi-sdk"),
        ]
        
        for loc in locations:
            if loc.exists() and (loc / "bin" / "clang").exists():
                return loc
        
        return None
    
    def run(self, wasm: bytes, config: Optional[SandboxConfig] = None) -> ExecutionResult:
        """
        Run WASM binary in sandbox.
        
        Args:
            wasm: WASM binary bytes
            config: Override sandbox configuration
            
        Returns:
            ExecutionResult
        """
        cfg = config or self.config
        
        with tempfile.TemporaryDirectory(prefix="shimmy_wasm_") as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create isolated /tmp for the sandbox
            sandbox_tmp = tmpdir / "sandbox_tmp"
            sandbox_tmp.mkdir()
            
            # Write WASM to temp file
            wasm_path = tmpdir / "program.wasm"
            wasm_path.write_bytes(wasm)
            
            # Build wasmtime command
            cmd = [
                "wasmtime", "run",
                "--fuel", str(cfg.fuel),
                "--wasm-timeout", f"{cfg.timeout}s",
                f"--max-memory-size={cfg.memory_mb}M",
            ]
            
            # WASI capability flags
            if not cfg.allow_clock:
                cmd.append("--wasi=cli:deny-clock")
            if not cfg.allow_random:
                cmd.append("--wasi=cli:deny-random")
            
            # Always provide isolated /tmp (mapped to sandbox_tmp)
            # WASM sees /tmp, but it's actually our isolated directory
            cmd.extend(["--dir", f"{sandbox_tmp}::/tmp"])
            
            # Track copied directories for ephemeral mode
            dir_copies = {}
            
            # Additional filesystem access
            if cfg.allow_fs_read or cfg.allow_fs_write:
                for dir_spec in cfg.allowed_dirs:
                    if ':' in dir_spec:
                        host_path, mode = dir_spec.rsplit(':', 1)
                    else:
                        host_path = dir_spec
                        mode = 'rw' if cfg.allow_fs_write else 'ro'
                    
                    host_path = Path(host_path).resolve()
                    
                    if cfg.ephemeral and mode == 'rw' and host_path.exists():
                        # Ephemeral mode: copy directory to temp location
                        # WASM writes to copy, original untouched
                        copy_dir = tmpdir / f"copy_{host_path.name}"
                        shutil.copytree(host_path, copy_dir)
                        dir_copies[str(host_path)] = copy_dir
                        cmd.extend(["--dir", f"{copy_dir}::{host_path}"])
                    elif mode == 'ro' or (not cfg.allow_fs_write):
                        cmd.extend(["--dir", f"{host_path}::ro"])
                    else:
                        # Non-ephemeral write: direct access (dangerous)
                        cmd.extend(["--dir", str(host_path)])
            
            # Environment variables (only if allowed)
            if cfg.allow_env:
                for key, value in cfg.env.items():
                    cmd.extend(["--env", f"{key}={value}"])
            
            # Add WASM file
            cmd.append(str(wasm_path))
            
            # Execute
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=cfg.timeout + 5,
                    input=cfg.stdin,
                )
                
                # Collect output files from sandbox /tmp
                output_files = {}
                if cfg.collect_output_files:
                    for f in sandbox_tmp.iterdir():
                        if f.is_file() and f.stat().st_size < cfg.max_output:
                            output_files[f.name] = f.read_bytes()
                    
                    # Optionally copy to output directory
                    if cfg.output_dir:
                        out_dir = Path(cfg.output_dir)
                        out_dir.mkdir(parents=True, exist_ok=True)
                        for name, data in output_files.items():
                            (out_dir / name).write_bytes(data)
                
                return ExecutionResult(
                    success=(result.returncode == 0),
                    returncode=result.returncode,
                    stdout=result.stdout[:cfg.max_output],
                    stderr=result.stderr[:cfg.max_output],
                    output_files=output_files,
                )
                
            except subprocess.TimeoutExpired:
                return ExecutionResult(
                    success=False,
                    returncode=-1,
                    stdout="",
                    stderr="",
                    error="Execution timed out",
                )
            except Exception as e:
                return ExecutionResult(
                    success=False,
                    returncode=-1,
                    stdout="",
                    stderr="",
                    error=str(e),
                )
            
            # Note: tempfile.TemporaryDirectory automatically cleans up
            # All writes in ephemeral mode are discarded here
    
    def exec(self, source: str, lang: Optional[Language] = None,
             config: Optional[SandboxConfig] = None) -> ExecutionResult:
        """
        Compile and run source code.
        
        Args:
            source: Source code string or file path
            lang: Programming language
            config: Sandbox configuration
            
        Returns:
            ExecutionResult
        """
        try:
            wasm = self.compile(source, lang)
            return self.run(wasm, config)
        except CompilerError as e:
            return ExecutionResult(
                success=False,
                returncode=-1,
                stdout="",
                stderr="",
                error=f"Compilation error: {e}",
            )

# ============================================================
# CLI
# ============================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Shimmy WASM Sandbox")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Compile command
    compile_parser = subparsers.add_parser("compile", help="Compile source to WASM")
    compile_parser.add_argument("source", help="Source file")
    compile_parser.add_argument("-o", "--output", help="Output WASM file")
    compile_parser.add_argument("--lang", choices=["c", "cpp", "rust", "go"])
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run WASM in sandbox")
    run_parser.add_argument("wasm", help="WASM file")
    run_parser.add_argument("--timeout", type=int, default=5)
    run_parser.add_argument("--memory", type=int, default=128)
    run_parser.add_argument("--fuel", type=int, default=1_000_000_000)
    run_parser.add_argument("--dir", action="append", dest="dirs", default=[])
    run_parser.add_argument("--env", action="append", dest="envs", default=[])
    run_parser.add_argument("--stdin", help="Input data")
    run_parser.add_argument("--json", action="store_true")
    
    # Exec command
    exec_parser = subparsers.add_parser("exec", help="Compile and run")
    exec_parser.add_argument("source", help="Source file")
    exec_parser.add_argument("--timeout", type=int, default=5)
    exec_parser.add_argument("--memory", type=int, default=128)
    exec_parser.add_argument("--lang", choices=["c", "cpp", "rust", "go"])
    exec_parser.add_argument("--json", action="store_true")
    
    args = parser.parse_args()
    
    sandbox = WasmSandbox()
    
    if args.command == "compile":
        lang = Language(args.lang) if args.lang else None
        output = Path(args.output) if args.output else Path(args.source).with_suffix(".wasm")
        try:
            wasm = sandbox.compile(args.source, lang, output)
            print(f"Compiled: {output} ({len(wasm)} bytes)")
        except CompilerError as e:
            print(f"Error: {e}")
            exit(1)
    
    elif args.command == "run":
        wasm = Path(args.wasm).read_bytes()
        
        env_dict = {}
        for e in args.envs:
            key, value = e.split("=", 1)
            env_dict[key] = value
        
        config = SandboxConfig(
            timeout=args.timeout,
            memory_mb=args.memory,
            fuel=args.fuel,
            allowed_dirs=args.dirs,
            env=env_dict,
            stdin=args.stdin,
        )
        
        result = sandbox.run(wasm, config)
        
        if args.json:
            print(json.dumps({
                "success": result.success,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "error": result.error,
            }))
        else:
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, file=sys.stderr, end="")
            if result.error:
                print(f"Error: {result.error}", file=sys.stderr)
            exit(result.returncode)
    
    elif args.command == "exec":
        lang = Language(args.lang) if args.lang else None
        config = SandboxConfig(timeout=args.timeout, memory_mb=args.memory)
        
        result = sandbox.exec(args.source, lang, config)
        
        if args.json:
            print(json.dumps({
                "success": result.success,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "error": result.error,
            }))
        else:
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, file=sys.stderr, end="")
            if result.error:
                print(f"Error: {result.error}", file=sys.stderr)
            exit(result.returncode if result.success else 1)

if __name__ == "__main__":
    import sys
    main()
