#include <stdio.h>
#include <math.h>

int main() {
    double sum = 0;
    for (int i = 1; i <= 1000; i++) {
        sum += sqrt(i);
    }
    printf("Sum of sqrt(1..1000) = %.2f\n", sum);
    return 0;
}
