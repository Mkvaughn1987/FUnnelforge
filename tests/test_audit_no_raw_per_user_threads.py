"""Regression net: any new threading.Thread(target=...) in flowdrip_app.py
that touches per-user state must use _run_as_user instead.

For each raw thread spawn, this test finds the WORKER function's body
(by walking indentation, not a flat line window) and scans only those
lines for per-user-write markers. This avoids false positives from
sibling functions that happen to live in the next 50 lines.

System threads (schedulers, monitors) and known no-write class methods
are allowlisted by name.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_FILE = REPO_ROOT / "flowdrip_app.py"

# Functions / patterns that indicate a per-user write is happening.
PER_USER_WRITE_MARKERS = [
    "save_candidate_pool",
    "save_dnc",
    "add_candidate_to_pool",
    "update_candidate_in_pool",
    "remove_candidate_from_pool",
    "_user_candidate_pool_path",
    "_user_pdf_dir",
    "_user_dnc_path",
    "_user_queue_path",
    "_user_config_path",
    "_user_signature_path",
    "_user_templates_dir",
    "_user_campaigns_dir",
    "_user_clients_path",
    "_user_newsletters_dir",
    "_user_responded_json",
    "_user_mi_results_path",
    "_user_mi_path",
    "_save_company_profile",
    "_save_pdf_sidecar",
    "_save_mi_results",
    "_save_mi_watches",
    "save_campaign",
    "save_config",
    "save_responded",
    "requeue_campaign",
    "_aicb_attach_pdfs",
    "_publish_pdf",
    "_rebuild_pdf_from_sidecar_data",
]

# Thread names that are known system-level (no user binding required).
SYSTEM_THREAD_NAMES = {
    "ServerEmailScheduler",
    "ServerReplyMonitor",
}

# Class-method workers that are correctly handled by other mechanisms:
# - OutlookMonitor._loop / ._scan: desktop-only, single-user (gated by _SERVER_MODE elsewhere)
# - CandidatePoolScanner._loop: server mode is gated inside _check_and_scan
ALLOWLISTED_METHOD_WORKERS = {
    "self._loop",
    "self._scan",
}

# Raw thread-spawn patterns we want to catch
SPAWN_PATTERNS = [
    re.compile(r"threading\.Thread\(target="),
    re.compile(r"_thr\.Thread\(target="),
    re.compile(r"_thr2\.Thread\(target="),
    re.compile(r"_th\.Thread\(target="),
    re.compile(r"_thr_pdf\.Thread\(target="),
]

# Fallback line window if we can't find the worker function definition
# (e.g. spawn target is a lambda or a method we can't statically resolve).
FALLBACK_LOOKAHEAD = 50


def _is_system_thread(spawn_line: str) -> bool:
    """A spawn is system-level if its name= argument is in the allowlist."""
    m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', spawn_line)
    if not m:
        return False
    return m.group(1) in SYSTEM_THREAD_NAMES


def _is_method_allowlisted(spawn_line: str) -> bool:
    """Spawn is allowlisted if its target= is a known no-write class method."""
    m = re.search(r'target\s*=\s*([\w.]+)', spawn_line)
    if not m:
        return False
    return m.group(1) in ALLOWLISTED_METHOD_WORKERS


def _extract_target_name(spawn_line: str) -> str | None:
    """Extract the bare function name from `target=<name>`."""
    m = re.search(r'target\s*=\s*([\w.]+)', spawn_line)
    if not m:
        return None
    return m.group(1).rsplit(".", 1)[-1]  # handle `self._loop` -> `_loop`


def _find_worker_body(src: list, spawn_idx: int, spawn_line: str):
    """Given a spawn line and its index, find the (start, end) line
    indices (exclusive end) of the target function's body. Returns
    None if the def can't be located within 200 lines preceding the
    spawn (e.g. lambda, method on a far-away class)."""
    fn_name = _extract_target_name(spawn_line)
    if not fn_name:
        return None
    pat = re.compile(r'^(\s*)def\s+' + re.escape(fn_name) + r'\s*\(')
    # Search backward
    search_start = max(spawn_idx - 200, 0)
    for j in range(spawn_idx - 1, search_start - 1, -1):
        m = pat.match(src[j])
        if m:
            def_indent = len(m.group(1))
            # Walk forward to find end of body
            for k in range(j + 1, len(src)):
                ll = src[k]
                if not ll.strip():
                    continue  # skip blank lines
                ll_indent = len(ll) - len(ll.lstrip())
                if ll_indent <= def_indent:
                    return (j, k)
            return (j, len(src))
    return None


def test_no_raw_thread_writes_per_user_state():
    """For each raw threading.Thread(target=...) spawn in flowdrip_app.py,
    locate the target function's body (by indentation) and verify it
    contains no per-user-write markers. If it does, that's a leak vector
    — the spawn must use _run_as_user instead.

    System threads (named in SYSTEM_THREAD_NAMES) and class-method
    workers (in ALLOWLISTED_METHOD_WORKERS) are skipped.
    """
    src = SOURCE_FILE.read_text(encoding="utf-8").splitlines()
    leaks = []
    for i, line in enumerate(src):
        if not any(p.search(line) for p in SPAWN_PATTERNS):
            continue
        if _is_system_thread(line):
            continue
        if _is_method_allowlisted(line):
            continue
        body = _find_worker_body(src, i, line)
        if body is not None:
            start, end = body
            window = "\n".join(src[start:end])
            scope = f"worker fn at L{start+1}"
        else:
            # Fallback: flat window if we can't find the def
            window = "\n".join(src[i : i + FALLBACK_LOOKAHEAD])
            scope = f"L{i+1}+{FALLBACK_LOOKAHEAD} (def not found)"
        for marker in PER_USER_WRITE_MARKERS:
            if marker in window:
                leaks.append(
                    f"  L{i+1}: {line.strip()[:80]}\n"
                    f"    → {scope} contains {marker!r}; "
                    f"migrate to _run_as_user(...) or add a system-thread "
                    f"name from SYSTEM_THREAD_NAMES."
                )
                break
    assert not leaks, (
        "Found raw threading.Thread spawns that do per-user writes "
        "without _run_as_user binding. Each is a cross-user leak vector:\n"
        + "\n".join(leaks)
    )
