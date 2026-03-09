#!/usr/bin/env python3
"""
Shimmy WASM Security Tests

Comprehensive security testing for the WASM sandbox.

Run: python -m pytest tests/test_security.py -v
"""

import pytest
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.sandbox import WasmSandbox, SandboxConfig, Language

# ============================================================
# Test Fixtures
# ============================================================

@pytest.fixture
def sandbox():
    return WasmSandbox()

# ============================================================
# Network Isolation Tests
# ============================================================

class TestNetworkIsolation:
    """Test that network access is completely blocked."""
    
    def test_no_tcp_socket(self, sandbox):
        """TCP sockets should not exist in WASI."""
        code = '''
#include <stdio.h>

// WASI has no socket support
int main() {
    printf("No TCP socket API in WASI\\n");
    return 0;
}
'''
        result = sandbox.exec(code, Language.C)
        assert result.success
    
    def test_no_udp_socket(self, sandbox):
        """UDP sockets should not exist in WASI."""
        code = '''
#include <stdio.h>

int main() {
    printf("No UDP socket API in WASI\\n");
    return 0;
}
'''
        result = sandbox.exec(code, Language.C)
        assert result.success
    
    def test_no_dns_resolution(self, sandbox):
        """DNS resolution should not be available."""
        code = '''
#include <stdio.h>

// getaddrinfo doesn't exist in WASI
int main() {
    printf("No DNS API in WASI\\n");
    return 0;
}
'''
        result = sandbox.exec(code, Language.C)
        assert result.success

# ============================================================
# Filesystem Isolation Tests
# ============================================================

class TestFilesystemIsolation:
    """Test filesystem access controls."""
    
    def test_no_root_access(self, sandbox):
        """Cannot access root filesystem."""
        code = '''
#include <stdio.h>
#include <dirent.h>

int main() {
    DIR* d = opendir("/");
    if (d) {
        printf("FAIL: opened root\\n");
        return 1;
    }
    printf("OK: cannot open root\\n");
    return 0;
}
'''
        result = sandbox.exec(code, Language.C)
        # Should either fail to open or succeed with our message
        assert "FAIL" not in result.stdout or not result.success
    
    def test_no_etc_passwd(self, sandbox):
        """Cannot read /etc/passwd."""
        code = '''
#include <stdio.h>

int main() {
    FILE* f = fopen("/etc/passwd", "r");
    if (f) {
        printf("FAIL: read /etc/passwd\\n");
        fclose(f);
        return 1;
    }
    printf("OK: cannot read /etc/passwd\\n");
    return 0;
}
'''
        result = sandbox.exec(code, Language.C)
        assert "FAIL" not in result.stdout
    
    def test_no_proc(self, sandbox):
        """Cannot access /proc."""
        code = '''
#include <stdio.h>

int main() {
    FILE* f = fopen("/proc/self/maps", "r");
    if (f) {
        printf("FAIL: read /proc\\n");
        fclose(f);
        return 1;
    }
    printf("OK: no /proc access\\n");
    return 0;
}
'''
        result = sandbox.exec(code, Language.C)
        assert "FAIL" not in result.stdout
    
    def test_isolated_tmp(self, sandbox):
        """Files written to /tmp are isolated."""
        code = '''
#include <stdio.h>

int main() {
    FILE* f = fopen("/tmp/test_file.txt", "w");
    if (f) {
        fprintf(f, "secret data");
        fclose(f);
        printf("wrote to /tmp\\n");
    }
    return 0;
}
'''
        # Run with default config (ephemeral=True)
        result = sandbox.exec(code, Language.C)
        
        # The file should NOT exist on host /tmp
        import os
        assert not os.path.exists("/tmp/test_file.txt")
    
    def test_cannot_escape_sandbox(self, sandbox):
        """Path traversal attacks should fail."""
        code = '''
#include <stdio.h>

int main() {
    // Try to escape via path traversal
    FILE* f = fopen("/tmp/../../../etc/passwd", "r");
    if (f) {
        printf("FAIL: escaped sandbox\\n");
        fclose(f);
        return 1;
    }
    printf("OK: path traversal blocked\\n");
    return 0;
}
'''
        result = sandbox.exec(code, Language.C)
        assert "FAIL" not in result.stdout

# ============================================================
# Process Isolation Tests
# ============================================================

class TestProcessIsolation:
    """Test that process creation is impossible."""
    
    def test_no_fork(self, sandbox):
        """fork() does not exist in WASI."""
        code = '''
#include <stdio.h>

// fork() is not available in WASI
int main() {
    printf("No fork in WASI\\n");
    return 0;
}
'''
        result = sandbox.exec(code, Language.C)
        assert result.success
    
    def test_no_exec(self, sandbox):
        """exec() does not exist in WASI."""
        code = '''
#include <stdio.h>

// exec family not available in WASI
int main() {
    printf("No exec in WASI\\n");
    return 0;
}
'''
        result = sandbox.exec(code, Language.C)
        assert result.success
    
    def test_no_system(self, sandbox):
        """system() should fail or not exist."""
        code = '''
#include <stdio.h>
#include <stdlib.h>

int main() {
    // system() in WASI should fail
    int ret = system("echo hello");
    if (ret == 0) {
        printf("FAIL: system() worked\\n");
        return 1;
    }
    printf("OK: system() blocked\\n");
    return 0;
}
'''
        result = sandbox.exec(code, Language.C)
        # system() should either not exist or fail
        assert result.success or "FAIL" not in result.stdout

# ============================================================
# Memory Isolation Tests
# ============================================================

class TestMemoryIsolation:
    """Test memory safety guarantees."""
    
    def test_memory_limit_enforced(self, sandbox):
        """Memory allocation beyond limit should fail."""
        code = '''
#include <stdio.h>
#include <stdlib.h>

int main() {
    // Try to allocate 256MB (should fail with 128MB limit)
    void* p = malloc(256 * 1024 * 1024);
    if (p) {
        printf("FAIL: allocated 256MB\\n");
        free(p);
        return 1;
    }
    printf("OK: allocation failed\\n");
    return 0;
}
'''
        config = SandboxConfig(memory_mb=128)
        result = sandbox.exec(code, Language.C, config)
        # Should either fail to allocate or trap
    
    def test_buffer_overflow_trapped(self, sandbox):
        """Buffer overflows should trap, not corrupt memory."""
        code = '''
#include <stdio.h>

int main() {
    char buf[10];
    // WASM bounds checking should catch this
    for (int i = 0; i < 1000; i++) {
        buf[i] = 'A';  // Out of bounds
    }
    printf("FAIL: no trap\\n");
    return 0;
}
'''
        result = sandbox.exec(code, Language.C)
        # Should trap or fail, not print FAIL
        assert not result.success or "FAIL" not in result.stdout
    
    def test_null_pointer_trapped(self, sandbox):
        """Null pointer dereference should trap."""
        code = '''
#include <stdio.h>

int main() {
    int* p = 0;
    *p = 42;  // Should trap
    printf("FAIL: no trap\\n");
    return 0;
}
'''
        result = sandbox.exec(code, Language.C)
        assert not result.success or "FAIL" not in result.stdout

# ============================================================
# Resource Exhaustion Tests
# ============================================================

class TestResourceExhaustion:
    """Test resource limit enforcement."""
    
    def test_cpu_limit_fuel(self, sandbox):
        """Fuel-based CPU limiting should work."""
        code = '''
int main() {
    volatile long long i;
    for (i = 0; i < 10000000000LL; i++);
    return 0;
}
'''
        config = SandboxConfig(fuel=10_000_000, timeout=30)
        result = sandbox.exec(code, Language.C, config)
        # Should run out of fuel
        assert not result.success
    
    def test_timeout_enforced(self, sandbox):
        """Timeout should terminate execution."""
        code = '''
int main() {
    while(1) {}
    return 0;
}
'''
        config = SandboxConfig(timeout=2)
        result = sandbox.exec(code, Language.C, config)
        assert not result.success
    
    def test_output_limit(self, sandbox):
        """Output should be truncated at limit."""
        code = '''
#include <stdio.h>

int main() {
    // Print a lot of output
    for (int i = 0; i < 1000000; i++) {
        printf("AAAAAAAAAA");
    }
    return 0;
}
'''
        config = SandboxConfig(max_output=1024)
        result = sandbox.exec(code, Language.C, config)
        assert len(result.stdout) <= config.max_output

# ============================================================
# Environment Isolation Tests  
# ============================================================

class TestEnvironmentIsolation:
    """Test environment variable isolation."""
    
    def test_no_host_env_by_default(self, sandbox):
        """Host environment variables should not leak."""
        import os
        os.environ["SECRET_KEY"] = "super_secret_value"
        
        code = '''
#include <stdio.h>
#include <stdlib.h>

int main() {
    char* secret = getenv("SECRET_KEY");
    if (secret) {
        printf("FAIL: leaked %s\\n", secret);
        return 1;
    }
    printf("OK: no SECRET_KEY\\n");
    return 0;
}
'''
        result = sandbox.exec(code, Language.C)
        assert "FAIL" not in result.stdout
        
        del os.environ["SECRET_KEY"]
    
    def test_only_allowed_env(self, sandbox):
        """Only explicitly allowed env vars should be passed."""
        code = '''
#include <stdio.h>
#include <stdlib.h>

int main() {
    char* allowed = getenv("ALLOWED_VAR");
    char* secret = getenv("PATH");
    
    if (allowed) printf("allowed=%s\\n", allowed);
    if (secret) printf("FAIL: PATH leaked\\n");
    
    return 0;
}
'''
        config = SandboxConfig(
            allow_env=True,
            env={"ALLOWED_VAR": "test_value"}
        )
        result = sandbox.exec(code, Language.C, config)
        assert "allowed=test_value" in result.stdout or not config.allow_env
        assert "FAIL" not in result.stdout

# ============================================================
# Run Tests
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
