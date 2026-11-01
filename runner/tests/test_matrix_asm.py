from pathlib import Path

import pytest

from app.build import MINIMAL_ENV, build_c
from app.jobs import CONTENT_ROOT
from app.sandbox import run

SOURCE = CONTENT_ROOT / "01-cpu-cache/snippets/matrix_sum_asm.c"
if not SOURCE.exists():
    SOURCE = Path(__file__).resolve().parents[2] / "content/01-cpu-cache/snippets/matrix_sum_asm.c"

CHECKS = r"""
#include <assert.h>
#include <stdlib.h>
extern int fn_a(const int *, int);
extern int fn_b(const int *, int);

static void check(const int *a, int n, int expected) {
    assert(fn_a(a, n) == expected);
    assert(fn_b(a, n) == expected);
}
int main(void) {
    check(NULL, 0, 0);
    check(NULL, -1, 0);
    const int sizes[] = {1, 2, 3, 7, 16, 17, 31, 64};
    for (unsigned k = 0; k < sizeof(sizes)/sizeof(sizes[0]); k++) {
        int n = sizes[k], count = n*n;
        int *a = calloc((size_t)count, sizeof(*a));
        assert(a);
        /* Each impulse must be visited exactly once, not skipped/repeated. */
        if (n <= 17) {
            for (int i = 0; i < count; i++) {
                a[i] = -37;
                check(a, n, -37);
                a[i] = 0;
            }
        }
        int expected = 0;
        for (int i = 0; i < count; i++) {
            a[i] = (i * 13 % 101) - 50;
            expected += a[i];
        }
        check(a, n, expected);
        free(a);
    }
    return 0;
}
"""


@pytest.mark.parametrize("optimization", ["-O0", "-O3"])
def test_both_assembly_traversals_visit_every_element(tmp_path, optimization):
    harness = tmp_path / "harness"
    harness.mkdir()
    (harness / "meta.yml").write_text("function: matrix_sum\n")
    (harness / "bench.c").write_text(CHECKS)
    source = SOURCE.read_text()
    build = build_c(
        tmp_path, harness,
        {"a": "#define MATRIX_COLUMNS 0\n" + source,
         "b": "#define MATRIX_COLUMNS 1\n" + source},
        [optimization, "-Wall", "-Wextra", "-Werror"], {},
    )
    result = run([str(build.binary)], tmp_path, timeout_s=10, memory_mb=256, env=MINIMAL_ENV)
    assert not result.timed_out
    assert result.returncode == 0, result.stderr
