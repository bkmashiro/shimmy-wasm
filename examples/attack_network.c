#include <stdio.h>
// This would fail - no network in WASI
// #include <sys/socket.h>

int main() {
    printf("No network access in WASM!\n");
    return 0;
}
