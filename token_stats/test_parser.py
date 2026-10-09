#!/usr/bin/env python3
"""
End-to-end test for the token-stats parser, driven by the test server.

Steps:
  1. Launch LaunchServerTest.bat (llama-server in router mode, port 8000,
     logging to token_stats/raw_test_server.log) as a background process.
  2. Wait for the server to come up, then send two chat completions to the
     model "Gemma4-12B-Q4-MTP":
        req 1: "What is 6 + 7? ..."            -> expect 13
        req 2: (req 1 as context) "now what is 6 * 7? ..." -> expect 42
     and verify each answer is correct.
  3. Stop the test server.
  4. Run parse_token_stats.py over the test log, producing
     token_stats/test_parsed_stats.md.
  5. Verify that exactly two requests were parsed and that the second
     request reported cached input tokens (> 0).
  6. If every check passed, delete the generated markdown, the test log, and
     the server output capture; otherwise keep them for manual inspection.

Usage:
    python token_stats/test_parser.py
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

# --- configuration ----------------------------------------------------------

MODEL = "Gemma4-12B-Q4-MTP"
BASE = "http://127.0.0.1:8000"

Q1 = "What is 6 + 7? return only the answer number, no formatting."
Q2 = "now what is 6 * 7? return only the answer number, no formatting."
EXPECTED_1 = "13"
EXPECTED_2 = "42"
MIN_OUTPUT_TPS = 50.0  # average output tok/s across the test requests


def script_dir():
    return os.path.dirname(os.path.abspath(__file__))


def main():
    sdir = script_dir()
    root = os.path.dirname(sdir)                      # workspace root
    bat = os.path.join(root, "LaunchServerTest.bat")
    parser = os.path.join(sdir, "parse_token_stats.py")
    log_path = os.path.join(sdir, "raw_test_server.log")
    md_path = os.path.join(sdir, "test_parsed_stats.md")
    out_path = os.path.join(sdir, "test_server_output.txt")

    # start fresh every run so the generated table only reflects this run
    for p in (md_path, log_path, out_path):
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError as e:
                print(f"[test] WARNING: could not remove {p}: {e}")

    results = {"q1_correct": False, "q2_correct": False,
               "request_count_ok": False, "second_cached_ok": False,
               "throughput_ok": False}
    resp1 = resp2 = ""
    server = None
    out_file = None

    try:
        # ---------------------------------------------------------- launch server
        print(f"[test] launching {bat}")
        # Console output (cmd stderr+stdout) is redirected to a file so a failed
        # launch can be inspected; writing to a file (not a pipe) avoids the
        # "unread pipe fills up and deadlocks the process" problem.
        out_file = open(out_path, "w", encoding="utf-8", errors="replace")
        # Run the .bat directly: on Windows CreateProcess routes .bat files
        # through cmd automatically, so no manual quoting is needed.
        server = subprocess.Popen(
            [bat],
            cwd=root,
            stdout=out_file,
            stderr=subprocess.STDOUT,
        )
        # NB: server.wait() in kill_server() will block until out_file is
        # closed -- see kill_server().

        print("[test] waiting for the server to start ...")
        if not wait_for_server(BASE, timeout=30):
            print("[test] ERROR: server did not become reachable on port 8000")
            print(f"[test] server process state: {server.poll()}")
            print(f"[test] last lines of {os.path.basename(out_path)}:")
            print_tail(out_path, n=20)
            return 1

        # ------------------------------------------------ request 1
        print(f"[test] sending request 1: {Q1!r}")
        try:
            resp1 = chat([{"role": "user", "content": Q1}])
        except Exception as e:
            print(f"[test] ERROR: request 1 failed: {trim(e)}")
            return 1
        results["q1_correct"] = has_number(resp1, EXPECTED_1)
        report("request 1 answer", resp1, EXPECTED_1, results["q1_correct"])

        # ------------------------------------------------ request 2 (with context)
        print(f"[test] sending request 2: {Q2!r}")
        messages = [
            {"role": "user", "content": Q1},
            {"role": "assistant", "content": resp1},
            {"role": "user", "content": Q2},
        ]
        try:
            resp2 = chat(messages)
        except Exception as e:
            print(f"[test] ERROR: request 2 failed: {trim(e)}")
            return 1
        results["q2_correct"] = has_number(resp2, EXPECTED_2)
        report("request 2 answer", resp2, EXPECTED_2, results["q2_correct"])

        # ------------------------------------------------ stop server
        print("[test] stopping test server ...")
        kill_server(server, out_file=out_file)
        server = None
        time.sleep(1)  # give it a moment to flush the log

        # ------------------------------------------------ run the parser
        print(f"[test] running parser on {os.path.basename(log_path)} ...")
        if not os.path.isfile(log_path):
            print(f"[test] ERROR: log file not found after run: {log_path}")
            return 1

        proc = subprocess.run(
            [sys.executable, parser, log_path, md_path],
            cwd=root,
        )
        if proc.returncode != 0:
            print(f"[test] ERROR: parser exited with code {proc.returncode}")
            return 1

        # ------------------------------------------------ verify parsed table
        rows = read_data_rows(md_path)
        results["request_count_ok"] = (len(rows) == 2)
        report("parsed request count", f"{len(rows)} row(s)", "2 rows",
               results["request_count_ok"])

        if len(rows) >= 2:
            try:
                cached2 = int(rows[1][1])  # "Cached" is the 2nd column
            except (ValueError, IndexError):
                cached2 = -1
            results["second_cached_ok"] = cached2 > 0
            report("second request cached tokens", str(cached2), "> 0",
                   results["second_cached_ok"])
        else:
            report("second request cached tokens", "n/a (no 2nd row)", "> 0", False)

        # ------------------------------------------------- average output tps
        # "Output tps" is the 8th column (index 7)
        tpss = []
        for row in rows:
            try:
                tpss.append(float(row[7]))
            except (ValueError, IndexError):
                pass
        if tpss:
            avg_tps = sum(tpss) / len(tpss)
            results["throughput_ok"] = avg_tps >= MIN_OUTPUT_TPS
            report("average output tok/s", f"{avg_tps:.2f}",
                   f">= {MIN_OUTPUT_TPS:g}", results["throughput_ok"])
        else:
            report("average output tok/s", "n/a (no tps values)",
                   f">= {MIN_OUTPUT_TPS:g}", False)

    except Exception as e:
        print(f"[test] ERROR: unexpected failure: {trim(e)}")
        return 1
    finally:
        if server is not None:
            kill_server(server, out_file=out_file)
            server = None

    # ------------------------------------------------ cleanup / verdict
    all_ok = all(results.values())
    print("\n[test] ===== RESULTS =====")
    for name, ok in results.items():
        print(f"[test]   {'PASS' if ok else 'FAIL'}  {name}")
    print("[test] ====================")

    if all_ok:
        for p in (md_path, log_path, out_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                    print(f"[test] deleted {os.path.basename(p)}")
                except OSError as e:
                    print(f"[test] WARNING: could not delete {p}: {e}")
        print("[test] all tests passed.")
        return 0

    print(f"[test] FAILURES detected. Keeping {os.path.basename(md_path)}, "
          f"{os.path.basename(log_path)} and "
          f"{os.path.basename(out_path)} for manual inspection.")
    return 1


# --- helpers ----------------------------------------------------------------

def wait_for_server(base, timeout):
    """Poll the server until it answers a request (model loading happens on
    the first chat call, so we only need the HTTP port to be up here)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/v1/models", timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def chat(messages, timeout=300):
    """Send a chat completion and return the assistant text.

    The first call triggers on-demand model load in router mode, so the timeout
    is generous. The answer may land in `content` or (for reasoning models)
    `reasoning_content`, so we return whichever is non-empty.
    """
    payload = json.dumps({
        "model": MODEL,
        "messages": messages,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    msg = data["choices"][0]["message"]
    content = (msg.get("content") or "").strip()
    if not content:
        content = (msg.get("reasoning_content") or "").strip()
    return content


def has_number(text, expected):
    """True if `expected` appears as a whole number token in `text`."""
    if not text:
        return False
    return re.search(rf"\b{re.escape(expected)}\b", text) is not None


def print_tail(path, n=20):
    """Print the last `n` lines of a file (prefixing each with [server]) to
    help debug launch failures."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()[-n:]
    except OSError as e:
        print(f"[test]   could not read file: {e}")
        return
    for ln in lines:
        print(f"[server] {ln}")


def read_data_rows(md_path):
    """Return the list of data rows (cells split by '|'), excluding the header
    row and the separator row. Assumes a freshly generated file (header first)."""
    if not os.path.isfile(md_path):
        return []
    with open(md_path, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip().startswith("|")]
    # lines[0] = header, lines[1] = separator
    rows = []
    for ln in lines[2:]:
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        rows.append(cells)
    return rows


def report(label, got, expected, ok):
    mark = "PASS" if ok else "FAIL"
    if ok:
        print(f"[test] {mark}  {label}: got {trim(got)}, expected {expected!r}")
    else:
        print(f"[test] {mark}  {label}: unexpected answer {trim(got)}, "
              f"expected {expected!r}")


def trim(text, limit=50):
    """For display: keep the first `limit` characters of `text` and note how
    much longer the original string was when it exceeds `limit`."""
    s = "" if text is None else str(text)
    if len(s) <= limit:
        return s
    return s[:limit] + f" ... (+{len(s) - limit} more chars, total {len(s)})"


def kill_server(server, out_file=None):
    """Terminate the server and its process tree (cmd -> llama-server).

    Also flushes/closes the output file handle if one was being written to,
    because server.wait() would otherwise block until the OS reclaims that
    handle (cmd inherits it for its own stdout/stderr, and the child
    llama-server may still be draining it after taskkill).
    """
    if server is None:
        return
    # Force-kill the FULL tree (cmd -> llama-server) while the parent process
    # is still alive. Calling server.terminate() first would kill only cmd;
    # cmd exits before the tree lookup and orphans the still-running
    # llama-server (keeping port 8000 and the log file open).
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(server.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
    try:
        # in the unlikely event the tree kill failed, fall back to a plain
        # terminate before reaping
        if server.poll() is None:
            server.kill()
    except Exception:
        pass
    try:
        server.wait(timeout=10)
    except Exception:
        pass
    if out_file is not None:
        try:
            out_file.flush()
            out_file.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
