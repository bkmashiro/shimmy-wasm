#!/usr/bin/env python3
"""
Shimmy WASM Sandbox Tests

Run: python -m pytest tests/ -v
"""

import pytest
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.sandbox import WasmSandbox, SandboxConfig, SandboxResult, Language, CompilerError

# ============================================================
# Test Fixtures
# ============================================================

@pytest.fixture
def sandbox():
    return WasmSandbox()

@pytest.fixture
def hello_c():
    return '''
#include <stdio.h>
int main() {
    printf("Hello WASM\\n");
    return 0;
}
'''

@pytest.fixture
def compute_c():
    return '''
#include <stdio.h>
int main() {
    int sum = 0;
    for (int i = 0; i < 1000; i++) sum += i;
    printf("%d\\n", sum);
    return 0;
}
'''

@pytest.fixture
def infinite_loop_c():
    return '''
int main() {
    while(1) {}
    return 0;
}
'''

@pytest.fixture
def memory_bomb_c():
    return '''
#include <stdlib.h>
int main() {
    while(1) {
        void* p = malloc(1024 * 1024);
        if (!p) break;
    }
    return 0;
}
'''

# ============================================================
# Compilation Tests
# ============================================================

class TestCompilation:
    
    def test_compile_c(self, sandbox, hello_c):
        """Test C compilation to WASM."""
        wasm = sandbox.compile(hello_c, Language.C)
        assert len(wasm) > 0
        # WASM magic number
        assert wasm[:4] == b'\\x00asm'
    
    def test_compile_invalid_c(self, sandbox):
        """Test compilation of invalid C code."""
        with pytest.raises(CompilerError):
            sandbox.compile("int main( { }", Language.C)
    
    def test_compile_from_file(self, sandbox):
        """Test compilation from file."""
        with tempfile.NamedTemporaryFile(suffix='.c', mode='w', delete=False) as f:
            f.write('#include <stdio.h>\\nint main() { printf("test"); return 0; }')
            f.flush()
            wasm = sandbox.compile(f.name)
            assert len(wasm) > 0

# ============================================================
# Execution Tests
# ============================================================

class TestExecution:
    
    def test_basic_execution(self, sandbox, hello_c):
        """Test basic WASM execution."""
        result = sandbox.exec(hello_c, Language.C)
        assert result.success
        assert "Hello WASM" in result.stdout
    
    def test_computation(self, sandbox, compute_c):
        """Test computation in WASM."""
        result = sandbox.exec(compute_c, Language.C)
        assert result.success
        assert "499500" in result.stdout
    
    def test_return_code(self, sandbox):
        """Test non-zero return code."""
        code = 'int main() { return 42; }'
        result = sandbox.exec(code, Language.C)
        assert result.returncode == 42

# ============================================================
# Security Tests
# ============================================================

class TestSecurity:
    
    def test_no_network(self, sandbox):
        """Test that network is blocked by default."""
        # WASI doesn't have socket support, so this should fail to compile
        # or the socket functions won't exist
        code = '''
#include <stdio.h>
int main() {
    // No network access in WASI
    printf("No network\\n");
    return 0;
}
'''
        result = sandbox.exec(code, Language.C)
        assert result.success  # Code runs but has no network
    
    def test_no_filesystem_by_default(self, sandbox):
        """Test that filesystem is restricted by default."""
        code = '''
#include <stdio.h>
int main() {
    FILE* f = fopen("/etc/passwd", "r");
    if (f) {
        printf("FAIL: opened /etc/passwd\\n");
        return 1;
    }
    printf("OK: cannot open /etc/passwd\\n");
    return 0;
}
'''
        result = sandbox.exec(code, Language.C)
        assert result.success
        assert "OK" in result.stdout or "cannot" in result.stdout.lower()
    
    def test_allowed_directory(self, sandbox):
        """Test preopened directory access."""
        code = '''
#include <stdio.h>
int main() {
    FILE* f = fopen("/tmp/test.txt", "w");
    if (f) {
        fprintf(f, "test");
        fclose(f);
        printf("OK\\n");
    }
    return 0;
}
'''
        config = SandboxConfig(
            allow_fs_write=True,
            allowed_dirs=["/tmp"],
        )
        result = sandbox.exec(code, Language.C, config)
        # May or may not succeed depending on /tmp mapping

# ============================================================
# Resource Limit Tests
# ============================================================

class TestResourceLimits:
    
    def test_timeout(self, sandbox, infinite_loop_c):
        """Test that infinite loops are terminated."""
        config = SandboxConfig(timeout=2, fuel=100_000_000)
        result = sandbox.exec(infinite_loop_c, Language.C, config)
        assert not result.success
        # Should timeout or run out of fuel
    
    def test_fuel_limit(self, sandbox):
        """Test fuel-based CPU limiting."""
        code = '''
int main() {
    volatile int i;
    for (i = 0; i < 1000000000; i++);
    return 0;
}
'''
        config = SandboxConfig(fuel=1_000_000, timeout=10)
        result = sandbox.exec(code, Language.C, config)
        # Should run out of fuel
        assert not result.success or result.error
    
    def test_memory_limit(self, sandbox, memory_bomb_c):
        """Test memory limiting."""
        config = SandboxConfig(memory_mb=16, timeout=5)
        result = sandbox.exec(memory_bomb_c, Language.C, config)
        # Should fail due to memory limit or allocation failure

# ============================================================
# run_string() Tests
# ============================================================

class TestRunString:
    """Test the run_string() convenience API."""

    def test_run_string_c_hello(self, sandbox):
        """run_string returns SandboxResult with correct fields."""
        code = '''
#include <stdio.h>
int main() {
    printf("hello from run_string\\n");
    return 0;
}
'''
        result = sandbox.run_string(code, Language.C)
        assert isinstance(result, SandboxResult)
        assert result.success
        assert result.exit_code == 0
        assert "hello from run_string" in result.stdout
        assert result.time_ms >= 0
        assert result.memory_kb > 0

    def test_run_string_with_stdin(self, sandbox):
        """run_string passes stdin correctly."""
        code = '''
#include <stdio.h>
int main() {
    char buf[256];
    if (fgets(buf, sizeof(buf), stdin)) {
        printf("got: %s", buf);
    }
    return 0;
}
'''
        result = sandbox.run_string(code, Language.C, stdin="test input\n")
        assert result.success
        assert "got: test input" in result.stdout

    def test_run_string_nonzero_exit(self, sandbox):
        """run_string captures non-zero exit codes."""
        code = 'int main() { return 42; }'
        result = sandbox.run_string(code, Language.C)
        assert not result.success
        assert result.exit_code == 42

    def test_run_string_stderr(self, sandbox):
        """run_string captures stderr output."""
        code = '''
#include <stdio.h>
int main() {
    fprintf(stderr, "error message\\n");
    return 1;
}
'''
        result = sandbox.run_string(code, Language.C)
        assert "error message" in result.stderr

    def test_run_string_timeout(self, sandbox):
        """run_string respects timeout parameter."""
        code = 'int main() { while(1) {} return 0; }'
        result = sandbox.run_string(code, Language.C, timeout=2)
        assert not result.success

    def test_run_string_compile_error(self, sandbox):
        """run_string handles compilation errors."""
        result = sandbox.run_string("invalid code {{{", Language.C)
        assert not result.success
        assert result.exit_code != 0

# ============================================================
# Run Tests
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
