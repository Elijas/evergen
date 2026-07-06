"""End-to-end specification of the evergen CLI, grouped by concern:

capture & mapping -> output-state machine -> header signing -> determinism ->
write safety. ``pytest -q --collect-only`` reads as the coverage checklist.
"""

from __future__ import annotations

import hashlib
import os
import stat
import sys
from pathlib import Path

import pytest

from evergen.cli import main


def write_gen(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "def gen():\n"
        f"    return {body!r}\n",
        encoding="utf-8",
    )


def run_evergen(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --- capture pattern & mapping ------------------------------------------------


def test_capture_pattern_mapping_nonrecursive_and_recursive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "one.eg.py", 'print("one")\n')
    write_gen(tmp_path / "src" / "pkg" / "two.eg.py", 'print("two")\n')

    code, out, err = run_evergen(capsys, "--output", "out/{}.py", "{}.eg.py")

    assert code == 0, err
    assert "WROTE out/one.py <- one.eg.py" in out
    assert (tmp_path / "out" / "one.py").exists()

    code, out, err = run_evergen(
        capsys, "--output", "{}__out.py", "src/**/{}.eg.py"
    )

    assert code == 0, err
    assert "WROTE src/pkg/two__out.py <- src/pkg/two.eg.py" in out
    assert (tmp_path / "src" / "pkg" / "two__out.py").exists()


def test_capture_does_not_cross_path_separators(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A non-recursive `{}` must match a single path segment only. `a/{}.eg.py`
    # must not capture `sub/x` for a nested `a/sub/x.eg.py`.
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "a" / "y.eg.py", 'print("y")\n')
    write_gen(tmp_path / "a" / "sub" / "x.eg.py", 'print("x")\n')

    code, out, err = run_evergen(capsys, "--output", "{}.py", "a/{}.eg.py")

    assert code == 0, err
    assert "WROTE y.py <- a/y.eg.py" in out
    assert (tmp_path / "y.py").exists()
    # The nested file must not have been captured as `sub/x`.
    assert "sub/x" not in out
    assert not (tmp_path / "sub" / "x.py").exists()


def test_dotted_generator_filename_is_loadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "summary.eg.py", 'print("summary")\n')

    code, out, err = run_evergen(capsys, "--output", "{}.out.py", "{}.eg.py")

    assert code == 0, err
    assert "WROTE summary.out.py <- summary.eg.py" in out
    assert 'print("summary")' in (tmp_path / "summary.out.py").read_text(
        encoding="utf-8"
    )


def test_duplicate_outputs_fail_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "a" / "same.eg.py", 'print("a")\n')
    write_gen(tmp_path / "b" / "same.eg.py", 'print("b")\n')

    code, out, err = run_evergen(
        capsys, "--output", "{}.py", "a/{}.eg.py", "b/{}.eg.py"
    )

    assert code == 1
    assert out == ""
    assert "ERROR duplicate output same.py" in err
    assert not (tmp_path / "same.py").exists()


def test_pattern_placeholder_validation_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # --output and every glob INPUT_PATTERN must contain exactly one {}
    # placeholder; zero or multiple placeholders are rejected up front, before
    # any planning or writing (README.md:162-164).
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "one.eg.py", "X = 1\n")

    code, out, err = run_evergen(capsys, "--output", "fixed.py", "{}.eg.py")
    assert code == 1
    assert out == ""
    assert "ERROR --output must contain exactly one {} placeholder" in err

    code, out, err = run_evergen(capsys, "--output", "{}/{}.py", "{}.eg.py")
    assert code == 1
    assert "ERROR --output must contain exactly one {} placeholder" in err

    code, out, err = run_evergen(capsys, "--output", "{}.py", "*.eg.py")
    assert code == 1
    assert (
        "ERROR input pattern '*.eg.py' must contain exactly one {} placeholder "
        "or be a plain .py file"
    ) in err

    code, out, err = run_evergen(capsys, "--output", "{}.py", "{}/{}.eg.py")
    assert code == 1
    assert (
        "ERROR input pattern '{}/{}.eg.py' must contain exactly one {} "
        "placeholder"
    ) in err
    assert "or be a plain .py file" not in err

    assert not (tmp_path / "one.py").exists()


def test_processing_and_reporting_order_is_sorted_regardless_of_input_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Matched generator paths are sorted before execution/reporting, regardless
    # of the order they were passed in or the order glob.glob happened to
    # return them (README.md:185).
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "zeta.eg.py", "Z = 1\n")
    write_gen(tmp_path / "alpha.eg.py", "A = 1\n")
    write_gen(tmp_path / "mu.eg.py", "M = 1\n")

    code, out, err = run_evergen(
        capsys, "--output", "{}.py", "zeta.eg.py", "alpha.eg.py", "mu.eg.py"
    )
    assert code == 0, err
    assert [line for line in out.splitlines() if line.startswith("WROTE")] == [
        "WROTE alpha.py <- alpha.eg.py",
        "WROTE mu.py <- mu.eg.py",
        "WROTE zeta.py <- zeta.eg.py",
    ]

    # A single glob pattern matching all three must still report sorted order.
    code, out, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")
    assert code == 0, err
    assert [line for line in out.splitlines() if line.startswith("WROTE")] == [
        "WROTE alpha.py <- alpha.eg.py",
        "WROTE mu.py <- mu.eg.py",
        "WROTE zeta.py <- zeta.eg.py",
    ]


# --- plain-file input capture ---------------------------------------------------


def test_plain_input_capture_suffix_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Plain-file capture strips the final .py and, when present, a trailing
    # generator suffix of .eg, .gen, or .generator; a bare .py with none of
    # those suffixes keeps its whole stem (README.md:256-259).
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "alpha.eg.py", 'print("alpha")\n')
    write_gen(tmp_path / "beta.gen.py", 'print("beta")\n')
    write_gen(tmp_path / "gamma.generator.py", 'print("gamma")\n')
    write_gen(tmp_path / "delta.py", 'print("delta")\n')

    for filename, capture in (
        ("alpha.eg.py", "alpha"),
        ("beta.gen.py", "beta"),
        ("gamma.generator.py", "gamma"),
        ("delta.py", "delta"),
    ):
        code, out, err = run_evergen(capsys, "--output", "out/{}.out.py", filename)
        assert code == 0, err
        assert f"WROTE out/{capture}.out.py <- {filename}" in out
        assert (tmp_path / "out" / f"{capture}.out.py").exists()

    code, out, err = run_evergen(capsys, "--output", "{}.py", "nonexistent.eg.py")
    assert code == 1
    assert "ERROR plain input file 'nonexistent.eg.py' does not exist" in err

    (tmp_path / "notes.txt").write_text("not python\n", encoding="utf-8")
    code, out, err = run_evergen(capsys, "--output", "{}.py", "notes.txt")
    assert code == 1
    assert "ERROR plain input file 'notes.txt' must end in .py" in err


# --- output-state machine: missing / clean / unmanaged / dirty -----------------


def test_default_write_states_missing_clean_unmanaged_and_dirty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "target.eg.py", 'print("generated")\n')

    code, out, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")

    assert code == 0, err
    assert "WROTE target.py <- target.eg.py" in out

    first_bytes = (tmp_path / "target.py").read_bytes()
    code, out, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")

    assert code == 0, err
    assert "WROTE target.py <- target.eg.py" in out
    assert (tmp_path / "target.py").read_bytes() == first_bytes

    write_gen(tmp_path / "manual.eg.py", 'print("generated")\n')
    (tmp_path / "manual.py").write_text("print('mine')\n", encoding="utf-8")

    code, out, _ = run_evergen(capsys, "--output", "{}.py", "manual.eg.py")

    assert code == 1
    assert "REFUSE manual.py <- manual.eg.py: not generated by evergen" in out

    (tmp_path / "target.py").write_text(
        (tmp_path / "target.py").read_text(encoding="utf-8") + "# edit\n",
        encoding="utf-8",
    )

    code, out, _ = run_evergen(capsys, "--output", "{}.py", "target.eg.py")

    assert code == 1
    assert "REFUSE target.py <- target.eg.py: hand-edited" in out


def test_check_reports_missing_dirty_stale_and_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "clean.eg.py", 'print("clean")\n')
    write_gen(tmp_path / "dirty.eg.py", 'print("dirty")\n')
    write_gen(tmp_path / "stale.eg.py", 'print("old")\n')
    write_gen(tmp_path / "missing.eg.py", 'print("missing")\n')

    code, _, err = run_evergen(
        capsys, "--output", "{}.py", "clean.eg.py", "dirty.eg.py", "stale.eg.py"
    )
    assert code == 0, err

    (tmp_path / "dirty.py").write_text(
        (tmp_path / "dirty.py").read_text(encoding="utf-8") + "# hand edit\n",
        encoding="utf-8",
    )
    write_gen(tmp_path / "stale.eg.py", 'print("new")\n')

    code, out, _ = run_evergen(
        capsys,
        "--check",
        "--output",
        "{}.py",
        "clean.eg.py",
        "dirty.eg.py",
        "stale.eg.py",
        "missing.eg.py",
    )

    assert code == 1
    assert "OK clean.py <- clean.eg.py" in out
    assert "DIRTY dirty.py <- dirty.eg.py" in out
    assert "STALE stale.py <- stale.eg.py: rerun evergen" in out
    assert "MISSING missing.py <- missing.eg.py: run evergen" in out

    code, out, err = run_evergen(capsys, "--output", "{}.py", "stale.eg.py")
    assert code == 0, err
    code, out, err = run_evergen(capsys, "--check", "--output", "{}.py", "stale.eg.py")
    assert code == 0, err
    assert "OK stale.py <- stale.eg.py" in out


def test_overwrite_replaces_unmanaged_and_dirty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "manual.eg.py", 'print("generated")\n')
    (tmp_path / "manual.py").write_text("print('mine')\n", encoding="utf-8")

    code, out, _ = run_evergen(capsys, "--output", "{}.py", "manual.eg.py")
    assert code == 1
    assert "not generated by evergen" in out

    code, out, err = run_evergen(
        capsys, "--overwrite", "--output", "{}.py", "manual.eg.py"
    )
    assert code == 0, err
    assert "OVERWROTE manual.py <- manual.eg.py" in out

    write_gen(tmp_path / "dirty.eg.py", 'print("fresh")\n')
    code, _, err = run_evergen(capsys, "--output", "{}.py", "dirty.eg.py")
    assert code == 0, err
    (tmp_path / "dirty.py").write_text(
        (tmp_path / "dirty.py").read_text(encoding="utf-8") + "# edit\n",
        encoding="utf-8",
    )

    code, out, _ = run_evergen(capsys, "--output", "{}.py", "dirty.eg.py")
    assert code == 1
    assert "hand-edited" in out

    code, out, err = run_evergen(
        capsys, "--overwrite", "--output", "{}.py", "dirty.eg.py"
    )
    assert code == 0, err
    assert "OVERWROTE dirty.py <- dirty.eg.py" in out


def test_overwrite_writes_fresh_signed_bytes_not_just_a_status_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # OVERWROTE must mean the file's bytes actually became the freshly
    # generated, signed output — not merely that the status line was printed
    # while stale/hand-edited bytes stayed on disk.
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "manual.eg.py", 'print("fresh")\n')
    (tmp_path / "manual.py").write_text("print('mine')\n", encoding="utf-8")

    code, out, err = run_evergen(
        capsys, "--overwrite", "--output", "{}.py", "manual.eg.py"
    )
    assert code == 0, err
    assert "OVERWROTE manual.py <- manual.eg.py" in out
    manual_content = (tmp_path / "manual.py").read_text(encoding="utf-8")
    assert manual_content.startswith("# @generated by evergen from manual.eg.py")
    assert 'print("fresh")' in manual_content
    assert "print('mine')" not in manual_content

    write_gen(tmp_path / "dirty.eg.py", 'print("v1")\n')
    code, _, err = run_evergen(capsys, "--output", "{}.py", "dirty.eg.py")
    assert code == 0, err
    (tmp_path / "dirty.py").write_text(
        (tmp_path / "dirty.py").read_text(encoding="utf-8") + "# hand edit\n",
        encoding="utf-8",
    )
    write_gen(tmp_path / "dirty.eg.py", 'print("v2")\n')

    code, out, err = run_evergen(
        capsys, "--overwrite", "--output", "{}.py", "dirty.eg.py"
    )
    assert code == 0, err
    assert "OVERWROTE dirty.py <- dirty.eg.py" in out
    dirty_content = (tmp_path / "dirty.py").read_text(encoding="utf-8")
    assert 'print("v2")' in dirty_content
    assert "# hand edit" not in dirty_content
    assert 'print("v1")' not in dirty_content

    # The overwritten file re-verifies as clean against the current generator.
    code, out, err = run_evergen(capsys, "--check", "--output", "{}.py", "dirty.eg.py")
    assert code == 0, err
    assert "OK dirty.py <- dirty.eg.py" in out


def test_check_is_read_only_across_missing_dirty_stale_unmanaged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # --check writes nothing: a MISSING output stays absent, and DIRTY/STALE/
    # UNMANAGED outputs keep their exact on-disk bytes (README.md:68,
    # "--check writes nothing"). This also covers the UNMANAGED status text,
    # which the existing STALE/DIRTY/MISSING/OK test does not exercise.
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "missing.eg.py", 'print("missing")\n')
    write_gen(tmp_path / "dirty.eg.py", 'print("dirty")\n')
    write_gen(tmp_path / "stale.eg.py", 'print("old")\n')

    code, _, err = run_evergen(
        capsys, "--output", "{}.py", "dirty.eg.py", "stale.eg.py"
    )
    assert code == 0, err

    (tmp_path / "dirty.py").write_text(
        (tmp_path / "dirty.py").read_text(encoding="utf-8") + "# hand edit\n",
        encoding="utf-8",
    )
    dirty_bytes = (tmp_path / "dirty.py").read_bytes()
    stale_bytes = (tmp_path / "stale.py").read_bytes()
    write_gen(tmp_path / "stale.eg.py", 'print("new")\n')
    (tmp_path / "unmanaged.py").write_text("hand written\n", encoding="utf-8")
    unmanaged_bytes = (tmp_path / "unmanaged.py").read_bytes()
    write_gen(tmp_path / "unmanaged.eg.py", 'print("unmanaged")\n')

    code, out, err = run_evergen(
        capsys,
        "--check",
        "--output",
        "{}.py",
        "missing.eg.py",
        "dirty.eg.py",
        "stale.eg.py",
        "unmanaged.eg.py",
    )

    assert code == 1
    assert "MISSING missing.py <- missing.eg.py: run evergen" in out
    assert "DIRTY dirty.py <- dirty.eg.py" in out
    assert "STALE stale.py <- stale.eg.py: rerun evergen" in out
    assert (
        "UNMANAGED unmanaged.py <- unmanaged.eg.py: not generated by evergen; "
        "use --overwrite to replace"
    ) in out

    # Nothing was written, rewritten, or touched.
    assert not (tmp_path / "missing.py").exists()
    assert (tmp_path / "dirty.py").read_bytes() == dirty_bytes
    assert (tmp_path / "stale.py").read_bytes() == stale_bytes
    assert (tmp_path / "unmanaged.py").read_bytes() == unmanaged_bytes


def test_write_mode_refusals_report_every_target_with_full_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A mixed write-mode run reports every target and exits nonzero, using the
    # full documented refusal message (graduation guidance for dirty, the
    # --overwrite pointer for unmanaged), while safe targets still process and
    # refused targets keep their exact hand-edited bytes (README.md:57-64,
    # 95-101).
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "clean.eg.py", 'print("clean")\n')
    write_gen(tmp_path / "dirty.eg.py", 'print("dirty")\n')
    write_gen(tmp_path / "unmanaged.eg.py", 'print("unmanaged")\n')
    write_gen(tmp_path / "missing.eg.py", 'print("missing")\n')

    code, _, err = run_evergen(
        capsys, "--output", "{}.py", "clean.eg.py", "dirty.eg.py"
    )
    assert code == 0, err

    (tmp_path / "dirty.py").write_text(
        (tmp_path / "dirty.py").read_text(encoding="utf-8") + "# hand edit\n",
        encoding="utf-8",
    )
    dirty_bytes = (tmp_path / "dirty.py").read_bytes()
    (tmp_path / "unmanaged.py").write_text("hand written\n", encoding="utf-8")
    unmanaged_bytes = (tmp_path / "unmanaged.py").read_bytes()

    code, out, err = run_evergen(
        capsys,
        "--output",
        "{}.py",
        "clean.eg.py",
        "dirty.eg.py",
        "unmanaged.eg.py",
        "missing.eg.py",
    )

    assert code == 1
    assert "WROTE clean.py <- clean.eg.py" in out
    assert (
        "REFUSE dirty.py <- dirty.eg.py: hand-edited; keep your edits by "
        "removing the header and deleting the generator, or discard them "
        "with --overwrite"
    ) in out
    assert (
        "REFUSE unmanaged.py <- unmanaged.eg.py: not generated by evergen; "
        "use --overwrite to replace"
    ) in out
    assert "WROTE missing.py <- missing.eg.py" in out

    assert (tmp_path / "dirty.py").read_bytes() == dirty_bytes
    assert (tmp_path / "unmanaged.py").read_bytes() == unmanaged_bytes
    assert (tmp_path / "missing.py").exists()


# --- signed header ------------------------------------------------------------


def test_header_decoration_still_detects_generated_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "asset.eg.py", "console.log('ok')\n")
    header = "// generated asset BodyHash<<{hash}>> from {source}"

    code, _, err = run_evergen(
        capsys, "--header", header, "--output", "{}.js", "{}.eg.py"
    )
    assert code == 0, err
    assert (tmp_path / "asset.js").read_text(encoding="utf-8").startswith(
        "// generated asset BodyHash<<"
    )

    code, out, err = run_evergen(
        capsys, "--check", "--header", header, "--output", "{}.js", "{}.eg.py"
    )
    assert code == 0, err
    assert "OK asset.js <- asset.eg.py" in out


def test_body_containing_its_own_token_round_trips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # If gen() output itself contains a BodyHash<<...>> token on an early line,
    # the real header is still line 1, so detection binds to it and a later
    # hand-edit of the body must still read DIRTY.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evil.eg.py").write_text(
        "def gen():\n"
        "    return '# BodyHash<<sha256:deadbeefdeadbeef>>\\nreal_code = 1\\n'\n",
        encoding="utf-8",
    )

    code, _, err = run_evergen(capsys, "--output", "{}.py", "evil.eg.py")
    assert code == 0, err

    code, out, err = run_evergen(capsys, "--check", "--output", "{}.py", "evil.eg.py")
    assert code == 0, err
    assert "OK evil.py <- evil.eg.py" in out

    output = tmp_path / "evil.py"
    output.write_text(
        output.read_text(encoding="utf-8").replace("real_code = 1", "real_code = 999"),
        encoding="utf-8",
    )
    code, out, _ = run_evergen(capsys, "--check", "--output", "{}.py", "evil.eg.py")
    assert code == 1
    assert "DIRTY evil.py <- evil.eg.py" in out


def test_default_header_hash_and_source_are_exact_and_absolute_output_honored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The default header line matches the documented template exactly,
    # {source} is the generator path relative to the output file's directory
    # (not the cwd), {hash} is the first 16 hex chars of SHA-256 over the body
    # alone, and an absolute --output pattern is honored as an absolute path
    # rather than joined to the cwd (README.md:191-199, 271).
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    write_gen(tmp_path / "src" / "thing.eg.py", "VALUE = 1\n")
    out_dir = tmp_path / "build" / "out"
    out_dir.mkdir(parents=True)
    abs_output_pattern = str(out_dir / "{}.py")

    code, out, err = run_evergen(
        capsys, "--output", abs_output_pattern, "src/thing.eg.py"
    )
    assert code == 0, err
    output = out_dir / "thing.py"
    assert output.exists()

    content = output.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    header_line = lines[0]
    body = "".join(lines[1:])
    assert body == "VALUE = 1\n"

    source_abs = (tmp_path / "src" / "thing.eg.py").resolve()
    expected_source = os.path.relpath(source_abs, output.resolve().parent).replace(
        os.sep, "/"
    )
    expected_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    expected_header_line = (
        f"# @generated by evergen from {expected_source} — "
        f"BodyHash<<sha256:{expected_hash}>> — do not hand-edit\n"
    )
    assert header_line == expected_header_line


def test_bodyhash_scan_window_and_hash_domain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Detection scans only the first five lines: a token there is recognized
    # regardless of what precedes it (e.g. a shebang), and the hash domain is
    # everything strictly AFTER the token's line, so that preamble is excluded
    # from the digest. A token beyond line 5 is not recognized at all, so the
    # file reads as unmanaged instead of clean (README.md:217-221).
    monkeypatch.chdir(tmp_path)
    body = "print('inner')\n"
    write_gen(tmp_path / "deep.eg.py", body)
    stored_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    header_line = f"# BodyHash<<sha256:{stored_hash}>>\n"

    # Token on line 5 (index 4): within the scan window. Two otherwise-clean
    # files differing only in the 4-line preamble above the token must both
    # read OK, because that preamble is outside the hash domain.
    preamble_a = "#!/usr/bin/env python3\n# a\n# a\n# a\n"
    (tmp_path / "deep.py").write_text(preamble_a + header_line + body, "utf-8")
    code, out, err = run_evergen(capsys, "--check", "--output", "{}.py", "deep.eg.py")
    assert code == 0, err
    assert "OK deep.py <- deep.eg.py" in out

    preamble_b = "#!/usr/bin/env python3\n# totally different\n# x\n# y\n"
    (tmp_path / "deep.py").write_text(preamble_b + header_line + body, "utf-8")
    code, out, err = run_evergen(capsys, "--check", "--output", "{}.py", "deep.eg.py")
    assert code == 0, err
    assert "OK deep.py <- deep.eg.py" in out

    # Token on line 6 (index 5): outside the 5-line scan window, so it is not
    # recognized at all -- unmanaged, not clean, even though the stored hash
    # would otherwise verify.
    preamble_5_lines = preamble_a + "# one more preamble line\n"
    (tmp_path / "deep.py").write_text(preamble_5_lines + header_line + body, "utf-8")
    code, out, err = run_evergen(capsys, "--check", "--output", "{}.py", "deep.eg.py")
    assert code == 1
    assert "UNMANAGED deep.py <- deep.eg.py" in out


def test_unknown_hash_algorithm_in_header_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The token names its algorithm (BodyHash<<algorithm:hex>>). A token naming
    # an algorithm this Python's hashlib does not provide (e.g. written by a
    # newer evergen) is an explicit ERROR pointing at the recovery paths, not a
    # silent guess at a state.
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "x.eg.py", "X = 1\n")
    (tmp_path / "x.py").write_text(
        "# BodyHash<<blake9:deadbeefdeadbeef>>\nX = 1\n", encoding="utf-8"
    )

    code, out, err = run_evergen(capsys, "--check", "--output", "{}.py", "x.eg.py")

    assert code == 1
    assert "unknown hash algorithm 'blake9'" in err
    assert "Traceback" not in err


# --- determinism ----------------------------------------------------------------


def test_two_runs_are_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "stable.eg.py", 'VALUE = 1\n')

    code, _, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")
    assert code == 0, err
    first = (tmp_path / "stable.py").read_bytes()

    code, _, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")
    assert code == 0, err

    assert (tmp_path / "stable.py").read_bytes() == first


def test_crlf_checked_out_output_is_not_dirty_or_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "line.eg.py", 'print("a")\nprint("b")\n')

    code, _, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")
    assert code == 0, err
    output = tmp_path / "line.py"
    output.write_bytes(output.read_bytes().replace(b"\n", b"\r\n"))

    code, out, err = run_evergen(capsys, "--check", "--output", "{}.py", "{}.eg.py")

    assert code == 0, err
    assert "OK line.py <- line.eg.py" in out


def test_generator_source_is_compiled_directly_not_stale_pycache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # evergen compiles generator source directly instead of going through the
    # __pycache__ machinery, so a pre-existing bytecode cache entry keyed on
    # (mtime, size) cannot serve stale code for a same-size edit made within
    # one mtime tick (README.md:209-211, "Determinism law").
    import py_compile

    monkeypatch.chdir(tmp_path)
    gen_path = tmp_path / "cache.eg.py"
    write_gen(gen_path, "OLD\n")

    # A real bytecode cache, keyed on this exact (mtime, size), as if some
    # other tool had already imported this file once.
    py_compile.compile(str(gen_path), doraise=True)
    assert (tmp_path / "__pycache__").is_dir()
    before = gen_path.stat()

    # Same-size content edit, mtime pinned back to its old value: a
    # timestamp-keyed bytecode cache would consider itself still valid.
    write_gen(gen_path, "NEW\n")
    os.utime(gen_path, (before.st_atime, before.st_mtime))
    assert gen_path.stat().st_size == before.st_size
    assert gen_path.stat().st_mtime == before.st_mtime

    code, out, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")

    assert code == 0, err
    generated = (tmp_path / "cache.py").read_text(encoding="utf-8")
    assert "NEW" in generated
    assert "OLD" not in generated


# --- write safety ---------------------------------------------------------------


def test_write_is_atomic_original_survives_failed_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A crash during the write must not corrupt an existing valid output. With an
    # atomic temp-file + os.replace strategy, a failure at replace leaves the
    # original bytes intact and no stray temp file behind. The write failure is
    # reported as a one-line ERROR for that target and exits nonzero rather than
    # escaping as a traceback (correctness F9).
    from evergen import cli

    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "atom.eg.py", 'VALUE = 1\n')

    code, _, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")
    assert code == 0, err
    output = tmp_path / "atom.py"
    original = output.read_bytes()

    # Regenerate with different content, but make the atomic swap fail.
    write_gen(tmp_path / "atom.eg.py", 'VALUE = 2\n')

    def boom(src: str, dst: str) -> None:
        raise OSError("simulated crash during rename")

    monkeypatch.setattr(cli.os, "replace", boom)
    code, out, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")

    assert code == 1
    assert "ERROR atom.py <- atom.eg.py: simulated crash during rename" in err

    # Original output is untouched, and no sibling temp file leaked.
    assert output.read_bytes() == original
    leaked = [p.name for p in tmp_path.iterdir() if p.name.startswith("atom.py.")]
    assert leaked == [], f"temp file leaked: {leaked}"


def test_write_os_error_reports_error_and_continues_with_remaining_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A filesystem error while writing one target is a one-line ERROR for that
    # target; the remaining targets still process, and the run exits nonzero
    # without a traceback (correctness F9).
    from evergen import cli

    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "a.eg.py", 'A = 1\n')
    write_gen(tmp_path / "b.eg.py", 'B = 1\n')

    real_replace = cli.os.replace
    calls = {"n": 0}

    def flaky(src: str, dst: str) -> None:
        calls["n"] += 1
        if calls["n"] == 1:  # first target (sorted: a before b) fails to replace.
            raise OSError("simulated write failure")
        real_replace(src, dst)

    monkeypatch.setattr(cli.os, "replace", flaky)
    code, out, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")

    assert code == 1
    assert "ERROR a.py <- a.eg.py: simulated write failure" in err
    assert "Traceback" not in err
    assert "WROTE b.py <- b.eg.py" in out
    assert (tmp_path / "b.py").exists()
    assert not (tmp_path / "a.py").exists()


def test_write_preserves_existing_file_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Rewriting a clean output keeps the target's existing mode (e.g. an
    # executable generated script), instead of resetting it to mkstemp's private
    # 0600 (correctness F5).
    if sys.platform == "win32":  # pragma: no cover - POSIX permission semantics.
        pytest.skip("POSIX permission bits")
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "script.eg.py", 'print(1)\n')

    code, _, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")
    assert code == 0, err
    output = tmp_path / "script.py"
    os.chmod(output, 0o755)

    code, out, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")
    assert code == 0, err
    assert "WROTE script.py <- script.eg.py" in out
    assert stat.S_IMODE(output.stat().st_mode) == 0o755


def test_new_file_gets_umask_permissions_not_private_0600(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A brand new output is created like a normal open() would (0666 & ~umask),
    # not with mkstemp's private 0600 (correctness F5).
    if sys.platform == "win32":  # pragma: no cover - POSIX permission semantics.
        pytest.skip("POSIX permission bits")
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "fresh.eg.py", 'VALUE = 1\n')

    umask = os.umask(0)
    os.umask(umask)
    expected = 0o666 & ~umask

    code, _, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")
    assert code == 0, err
    mode = stat.S_IMODE((tmp_path / "fresh.py").stat().st_mode)
    assert mode == expected, oct(mode)
    assert mode != 0o600


# --- generator loading: sys.modules, encodings, sibling imports ----------------


def test_generator_using_dataclass_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The generator module is registered in sys.modules while it executes, so
    # ordinary Python that inspects sys.modules[cls.__module__] — @dataclass does
    # — works instead of crashing (correctness F7).
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dc.eg.py").write_text(
        "from dataclasses import dataclass\n"
        "\n"
        "@dataclass\n"
        "class Row:\n"
        "    name: str\n"
        "\n"
        "def gen():\n"
        '    return Row("ok").name + "\\n"\n',
        encoding="utf-8",
    )

    code, out, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")

    assert code == 0, err
    assert "WROTE dc.py <- dc.eg.py" in out
    assert "ok" in (tmp_path / "dc.py").read_text(encoding="utf-8")
    # The temporary module name must not leak into sys.modules afterwards.
    assert not any(name.startswith("_evergen_") for name in sys.modules)


def test_generator_module_name_restored_after_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # sys.path and sys.modules are restored after loading a generator.
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "clean.eg.py", 'X = 1\n')
    before_path = list(sys.path)

    code, _, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")

    assert code == 0, err
    assert list(sys.path) == before_path


def test_generator_source_honors_encoding_cookie_and_bom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Source is compiled from bytes so Python's own decoding handles a PEP 263
    # coding cookie and a UTF-8 BOM instead of crashing on a strict utf-8 read
    # (correctness F8).
    monkeypatch.chdir(tmp_path)
    (tmp_path / "latin.eg.py").write_bytes(
        b'# -*- coding: latin-1 -*-\n\ndef gen():\n    return "caf\xe9\\n"\n'
    )
    (tmp_path / "bom.eg.py").write_bytes(
        b"\xef\xbb\xbfdef gen():\n    return \"ok\\n\"\n"
    )

    code, out, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")

    assert code == 0, err
    assert "café" in (tmp_path / "latin.py").read_text(encoding="utf-8")
    assert "ok" in (tmp_path / "bom.py").read_text(encoding="utf-8")


def test_generator_can_import_sibling_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A nested generator can import a sibling module by ordinary absolute import,
    # because the generator's directory is placed on sys.path while it runs
    # (correctness F3).
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "helper.py").write_text('VALUE = "ok"\n', encoding="utf-8")
    (tmp_path / "pkg" / "item.eg.py").write_text(
        'from helper import VALUE\n\ndef gen():\n    return VALUE + "\\n"\n',
        encoding="utf-8",
    )

    code, out, err = run_evergen(capsys, "--output", "{}.py", "pkg/{}.eg.py")

    assert code == 0, err
    assert "WROTE item.py <- pkg/item.eg.py" in out
    assert "ok" in (tmp_path / "item.py").read_text(encoding="utf-8")


def test_same_named_siblings_do_not_leak_between_generators(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Sibling modules are evicted from sys.modules after each generator runs.
    # Without eviction, two generators in different directories importing a
    # same-named sibling would share whichever loaded first, so output would
    # depend on co-invocation and break the determinism law.
    monkeypatch.chdir(tmp_path)
    for dirname, value in (("dira", "A"), ("dirb", "B")):
        subdir = tmp_path / dirname
        subdir.mkdir()
        (subdir / "helper.py").write_text(f'VALUE = "{value}"\n', encoding="utf-8")
        (subdir / "item.eg.py").write_text(
            'from helper import VALUE\n\ndef gen():\n    return VALUE + "\\n"\n',
            encoding="utf-8",
        )

    code, out, err = run_evergen(capsys, "--output", "{}_out.py", "**/{}.eg.py")

    assert code == 0, err
    assert "A" in (tmp_path / "dira" / "item_out.py").read_text(encoding="utf-8")
    assert "B" in (tmp_path / "dirb" / "item_out.py").read_text(encoding="utf-8")


def test_generator_import_time_error_is_reported_not_tracebacked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # An exception raised while executing the generator body (import time) is a
    # one-line ERROR, not a traceback (correctness F3).
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bad.eg.py").write_text(
        "from nonexistent_sibling import thing\n\ndef gen():\n    return thing\n",
        encoding="utf-8",
    )

    code, out, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")

    assert code == 1
    assert "failed to import" in err
    assert "Traceback" not in err
    assert not (tmp_path / "bad.py").exists()


# --- glob character classes ----------------------------------------------------


def test_glob_character_range_matches_are_all_processed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A glob character range like [a-z] must process every file glob matched,
    # not silently drop the ones a too-narrow capture regex missed
    # (correctness F2).
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "aone.eg.py", 'A = 1\n')
    write_gen(tmp_path / "btwo.eg.py", 'B = 1\n')

    code, out, err = run_evergen(capsys, "--output", "{}.py", "[a-z]{}.eg.py")

    assert code == 0, err
    assert "WROTE one.py <- aone.eg.py" in out
    assert "WROTE two.py <- btwo.eg.py" in out
    assert (tmp_path / "one.py").exists()
    assert (tmp_path / "two.py").exists()


# --- classify before executing the generator (state precedence) ----------------


def test_dirty_target_refused_without_running_generator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A dirty target is refused (without --overwrite) from its on-disk state
    # alone; the generator — which here would fail — never runs
    # (correctness F6 / security F7).
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "x.eg.py", 'X = 1\n')

    code, _, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")
    assert code == 0, err
    output = tmp_path / "x.py"
    output.write_text(output.read_text(encoding="utf-8") + "# hand edit\n", "utf-8")

    # Replace the generator with one that fails at import time and marks that it
    # ran. Classification must refuse before any of that happens.
    (tmp_path / "x.eg.py").write_text(
        "from pathlib import Path\n"
        'Path("gen_ran.txt").write_text("ran", encoding="utf-8")\n'
        "\n"
        "def gen():\n"
        '    raise RuntimeError("boom")\n',
        encoding="utf-8",
    )

    code, out, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")

    assert code == 1
    assert "REFUSE x.py <- x.eg.py: hand-edited" in out
    assert "Traceback" not in err
    assert "gen() failed" not in (out + err)
    assert not (tmp_path / "gen_ran.txt").exists()


def test_refused_target_does_not_block_other_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # One refused target still lets the others process; every target is reported
    # and the run exits nonzero (correctness F6).
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "a.eg.py", 'A = 1\n')
    write_gen(tmp_path / "b.eg.py", 'B = 1\n')
    (tmp_path / "a.py").write_text("hand written\n", encoding="utf-8")  # unmanaged.

    code, out, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")

    assert code == 1
    assert "REFUSE a.py <- a.eg.py: not generated by evergen" in out
    assert "WROTE b.py <- b.eg.py" in out
    assert (tmp_path / "b.py").exists()


def test_check_reports_dirty_without_running_generator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # In --check, DIRTY is decided from the file's on-disk state without running
    # the generator (correctness F6).
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dirty.py").write_text(
        "# BodyHash<<sha256:deadbeefdeadbeef>>\nbody = 1\n", encoding="utf-8"
    )
    (tmp_path / "dirty.eg.py").write_text(
        "from pathlib import Path\n"
        'Path("gen_ran.txt").write_text("ran", encoding="utf-8")\n'
        "\n"
        "def gen():\n"
        '    raise RuntimeError("boom")\n',
        encoding="utf-8",
    )

    code, out, err = run_evergen(capsys, "--check", "--output", "{}.py", "{}.eg.py")

    assert code == 1
    assert "DIRTY dirty.py <- dirty.eg.py" in out
    assert "Traceback" not in err
    assert not (tmp_path / "gen_ran.txt").exists()


def test_write_rechecks_state_before_atomic_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # TOCTOU narrowing: if a clean target turns dirty between classification and
    # the write, the re-read immediately before the atomic write refuses it
    # instead of clobbering the new edit (security F7).
    from evergen import cli

    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "x.eg.py", 'X = 1\n')

    code, _, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")
    assert code == 0, err
    output = tmp_path / "x.py"
    clean_bytes = output.read_bytes()

    real_state = cli.read_existing_state
    calls = {"n": 0}

    def flaky(path: Path):  # first call classifies clean; the re-read is dirty.
        calls["n"] += 1
        if calls["n"] == 1:
            return real_state(path)
        return cli.ExistingState("dirty", body="tampered\n", stored_hash="0" * 16)

    monkeypatch.setattr(cli, "read_existing_state", flaky)
    code, out, _ = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")

    assert code == 1
    assert "REFUSE x.py <- x.eg.py: hand-edited" in out
    assert output.read_bytes() == clean_bytes


# --- non-UTF-8 existing targets ------------------------------------------------


def test_non_utf8_existing_target_is_unmanaged_and_overwritable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # An existing output that is not valid UTF-8 has no readable BodyHash
    # token, so it classifies as unmanaged: refused without --overwrite (no
    # traceback), replaced with it (correctness F1).
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "x.eg.py", 'X = 1\n')
    (tmp_path / "x.py").write_bytes(b"\xff\xfe\x00\x01")

    code, out, err = run_evergen(capsys, "--output", "{}.py", "{}.eg.py")
    assert code == 1
    assert "REFUSE x.py <- x.eg.py: not generated by evergen" in out
    assert "Traceback" not in err

    code, out, err = run_evergen(
        capsys, "--overwrite", "--output", "{}.py", "{}.eg.py"
    )
    assert code == 0, err
    assert "OVERWROTE x.py <- x.eg.py" in out
    assert "X = 1" in (tmp_path / "x.py").read_text(encoding="utf-8")


# --- header validation ---------------------------------------------------------


def test_invalid_header_rejected_before_running_any_generator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A --header template missing the recognizable token is rejected up front,
    # before any generator is discovered or executed (correctness F4).
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.eg.py").write_text(
        "from pathlib import Path\n"
        'Path("gen_ran.txt").write_text("ran", encoding="utf-8")\n'
        "\n"
        "def gen():\n"
        '    return "ok\\n"\n',
        encoding="utf-8",
    )

    code, out, err = run_evergen(
        capsys, "--header", "hash={hash}", "--output", "{}.py", "{}.eg.py"
    )

    assert code == 1
    assert "BodyHash<<{hash}>>" in err
    assert not (tmp_path / "gen_ran.txt").exists()
    assert not (tmp_path / "x.py").exists()


def test_header_format_lookup_errors_are_rewrapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # str.format attribute/index lookups can raise AttributeError/IndexError/
    # TypeError; those become a one-line ERROR, not a traceback (security F6).
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "x.eg.py", 'X = 1\n')

    code, out, err = run_evergen(
        capsys,
        "--header",
        "BodyHash<<{hash}>> {source.nope}",
        "--output",
        "{}.py",
        "{}.eg.py",
    )

    assert code == 1
    assert "invalid --header TEMPLATE" in err
    assert "Traceback" not in err


def test_header_without_source_placeholder_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # {source} is optional in --header TEMPLATE; a template that omits it must
    # still render, sign, and round-trip clean (README.md:202-203).
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "asset.eg.py", "body\n")

    code, out, err = run_evergen(
        capsys,
        "--header",
        "// BodyHash<<{hash}>>",
        "--output",
        "{}.js",
        "{}.eg.py",
    )
    assert code == 0, err
    expected_hash = hashlib.sha256(b"body\n").hexdigest()[:16]
    content = (tmp_path / "asset.js").read_text(encoding="utf-8")
    assert content.splitlines()[0] == f"// BodyHash<<sha256:{expected_hash}>>"

    code, out, err = run_evergen(
        capsys,
        "--check",
        "--header",
        "// BodyHash<<{hash}>>",
        "--output",
        "{}.js",
        "{}.eg.py",
    )
    assert code == 0, err
    assert "OK asset.js <- asset.eg.py" in out


def test_multiline_header_template_is_rejected_before_generator_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # --header TEMPLATE must be a single line; rejected up front, before any
    # generator is discovered or executed (README.md:202-203).
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.eg.py").write_text(
        "from pathlib import Path\n"
        'Path("gen_ran.txt").write_text("ran", encoding="utf-8")\n'
        "\n"
        "def gen():\n"
        '    return "ok\\n"\n',
        encoding="utf-8",
    )

    code, out, err = run_evergen(
        capsys,
        "--header",
        "BodyHash<<{hash}>>\nextra line",
        "--output",
        "{}.py",
        "{}.eg.py",
    )

    assert code == 1
    assert "single line" in err
    assert not (tmp_path / "gen_ran.txt").exists()
    assert not (tmp_path / "x.py").exists()


# --- path blast radius ---------------------------------------------------------


def test_dotdot_capture_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A capture that resolves to ".." would retarget the write outside the
    # apparent output tree; reject it before substitution (security F2).
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / "...x.eg.py", 'X = 1\n')

    code, out, err = run_evergen(
        capsys, "--output", "out/{}/generated.py", ".{}x.eg.py"
    )

    assert code == 1
    assert "'..'" in err
    assert not (tmp_path / "generated.py").exists()


def test_empty_capture_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A plain input like ".eg.py" strips down to an empty capture, which would
    # write a file literally named ".py"; reject it like "." and "..".
    monkeypatch.chdir(tmp_path)
    write_gen(tmp_path / ".eg.py", "X = 1\n")

    code, out, err = run_evergen(capsys, "--output", "{}.py", ".eg.py")

    assert code == 1
    assert "''" in err
    assert not (tmp_path / ".py").exists()


def test_output_equals_source_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A mapping whose output resolves onto its own generator is refused up front,
    # so --overwrite --output '{}.py' '{}.py' cannot destroy the generator
    # (security F5).
    monkeypatch.chdir(tmp_path)
    tool = tmp_path / "tool.py"
    tool.write_text("def gen():\n    return \"print(1)\\n\"\n", encoding="utf-8")
    original = tool.read_bytes()

    code, out, err = run_evergen(
        capsys, "--overwrite", "--output", "{}.py", "{}.py"
    )

    assert code == 1
    assert "same file as its generator" in err
    assert tool.read_bytes() == original


# --- packaging ------------------------------------------------------------------


def test_version_matches_pyproject_project_version() -> None:
    # Guards against the console-script/package version and the packaged
    # pyproject.toml [project].version drifting apart on release.
    tomllib = pytest.importorskip("tomllib")
    from evergen import __version__

    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    assert __version__ == data["project"]["version"]
