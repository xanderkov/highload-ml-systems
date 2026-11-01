import pytest

from app.build import CompileError, build_c, native_flag

HARNESS = "tests/fixtures/harness/sumtest"

DEFINES = {"BENCH_WARMUP": 1, "BENCH_REPEATS": 2, "BENCH_SIZES": "{1000}", "BENCH_NSIZES": 1}


def read(name):
    with open(f"tests/fixtures/snippets/{name}", encoding="utf-8") as handle:
        return handle.read()


def test_native_flag_is_supported_by_compiler():
    flag = native_flag()
    assert flag in {"-march=native", "-mcpu=native", ""}


def test_build_produces_runnable_binary(tmp_path):
    result = build_c(
        tmp_path,
        HARNESS,
        {"a": read("sumtest_slow.c"), "b": read("sumtest_fast.c")},
        cflags=["-O2"],
        defines=DEFINES,
    )

    assert result.binary.exists()
    assert "-O2" in result.compile_command


def test_build_reports_compile_error_with_line(tmp_path):
    with pytest.raises(CompileError) as exc:
        build_c(
            tmp_path,
            HARNESS,
            {"a": read("sumtest_slow.c"), "b": "double total(const double *d, int n) { syntax error }"},
            cflags=["-O2"],
            defines=DEFINES,
        )

    assert exc.value.line == 1
    assert exc.value.unit == "b"
    assert "error" in exc.value.log


def test_compile_error_in_baseline_unit_is_not_attributed_to_student(tmp_path):
    # "a" is the baseline by job-format convention, not the student's own
    # submission. A broken baseline must still raise CompileError, but the
    # exception must record unit="a" so the caller (jobs.run_job) knows not
    # to hand this line number to the student.
    with pytest.raises(CompileError) as exc:
        build_c(
            tmp_path,
            HARNESS,
            {"a": "double total(const double *d, int n) { syntax error }", "b": read("sumtest_fast.c")},
            cflags=["-O2"],
            defines=DEFINES,
        )

    assert exc.value.unit == "a"


def test_compile_error_in_harness_stage_has_no_line_or_unit(tmp_path):
    # Both units compile cleanly on their own; the harness's own bench.c is
    # broken instead. A harness-stage failure must never carry a line
    # number or unit that looks like it points at student code.
    with pytest.raises(CompileError) as exc:
        build_c(
            tmp_path,
            "tests/fixtures/harness/broken_bench",
            {"a": read("sumtest_slow.c"), "b": read("sumtest_fast.c")},
            cflags=["-O2"],
            defines=DEFINES,
        )

    assert exc.value.unit is None
    assert exc.value.line is None
