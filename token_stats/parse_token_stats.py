#!/usr/bin/env python3
"""
Parses a llama.cpp server log (router mode) and appends per-request token stats
to a Markdown table file.

For each request it records:
  - model                 : from "proxying request to model <name> on port <port>"
  - cached_input_tokens   : "N cached" from the prompt eval line
  - input_tokens          : processed prompt tokens from the prompt eval line
  - output_tokens         : generated tokens from the eval line
  - prompt_eval_time_ms   : prompt eval time (ms)
  - eval_time_ms          : eval time (ms)
  - prompt_tokens_per_second
  - output_tokens_per_second

The Markdown table is appended to. The header row (and separator) is written
only if the file does not yet exist or is empty.

Usage:
    python parse_token_stats.py [logfile] [mdfile] [--delete]

Defaults (relative to this script's directory):
    logfile = raw_server.log
    mdfile  = parsed_request_stats.md

Options:
    --delete   delete the log file after successfully appending to the Markdown
"""
import datetime
import os
import re
import sys

# --- regexes ---------------------------------------------------------------

# "0.32.312.339 I srv  proxy_reques: proxying request to model Qwen3.8-27B-medium on port 56613"
RE_MODEL = re.compile(r"proxying request to model (\S+) on port (\d+)")

# "prompt eval time =     650.22 ms /   677 tokens (    0.96 ms per token,  1041.18 tokens per second,     0 cached)"
# groups: 1=prompt_eval_time_ms  2=input_tokens  3=prompt_tps  4=cached
RE_PROMPT = re.compile(
    r"prompt eval time =\s+([\d.]+)\s*ms\s*/\s*(\d+)\s*tokens"
    r"\s*\(\s*[\d.]+\s*ms per token,\s*([\d.]+)\s*tokens per second,\s*(\d+)\s*cached\)"
)

# "       eval time =    4182.82 ms /   320 tokens (   13.11 ms per token,    76.26 tokens per second)"
# groups: 1=eval_time_ms  2=output_tokens  3=output_tps
# The lookbehind prevents matching the "prompt eval time" line.
RE_EVAL = re.compile(
    r"(?<!prompt )eval time =\s+([\d.]+)\s*ms\s*/\s*(\d+)\s*tokens"
    r"\s*\(\s*[\d.]+\s*ms per token,\s*([\d.]+)\s*tokens per second\)"
)

# leading timestamp "M.SS.mmm.uuu" (minutes.seconds.milliseconds.microseconds),
# optionally preceded by a "[PORT] " prefix (child server lines).
# The prefix is only consumed when brackets are actually present, so multi-digit
# minutes (e.g. "13.03.733.797") are not partially eaten by the prefix match.
RE_TS = re.compile(r"^(?:\[\d+\]\s*)?(\d+)\.(\d+)\.(\d+)\.(\d+)")


def ts_to_seconds(m):
    """Convert a matched M.SS.mmm.uuu timestamp to total seconds."""
    mins, secs, ms, us = (int(m.group(i)) for i in range(1, 5))
    return mins * 60 + secs + ms / 1000.0 + us / 1000000.0


def set_creation_time_now(path):
    """Set a file's creation (birth) time to 'now' on Windows.

    NTFS 'tunneling' can make a recreated file (same name as a recently deleted
    one) inherit a stale creation time cached in the USN journal. Bumping the
    creation time to now right before deletion makes the tunneled value
    approximately correct for the next run. No-op on other platforms.
    """
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD),
                    ("dwHighDateTime", wintypes.DWORD)]

    k32 = ctypes.windll.kernel32
    k32.CreateFileW.restype = ctypes.c_void_p
    k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    ]
    k32.SetFileTime.restype = wintypes.BOOL
    k32.SetFileTime.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME),
    ]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]

    # Open with FILE_WRITE_ATTRIBUTES so SetFileTime is permitted.
    FILE_WRITE_ATTRIBUTES = 0x0100
    OPEN_EXISTING = 3
    h = k32.CreateFileW(path, FILE_WRITE_ATTRIBUTES, 0, None, OPEN_EXISTING, 0, None)
    if h is None:
        return

    # FILETIME = 100ns intervals since 1601-01-01 UTC = unix*1e7 + 11644473600e7
    unix = datetime.datetime.now().timestamp()
    ft = int(round(unix * 10_000_000)) + 11644473600 * 10_000_000
    filetime = FILETIME(ft & 0xFFFFFFFF, (ft >> 32) & 0xFFFFFFFF)

    k32.SetFileTime(h, ctypes.byref(filetime), None, None)
    k32.CloseHandle(h)


# data keys (used to index each row dict)
KEYS = [
    "model",
    "cached_input_tokens",
    "input_tokens",
    "output_tokens",
    "prompt_eval_time_ms",
    "eval_time_ms",
    "prompt_tokens_per_second",
    "output_tokens_per_second",
    "datetime",
]

# short, readable column names shown in the Markdown table
HEADER = [
    "Model",
    "Cached",
    "Input",
    "Output",
    "Prompt ms",
    "Output ms",
    "Prompt tps",
    "Output tps",
    "Date",
]


def parse(log_path):
    """Yield one dict per completed request found in the log."""
    current_model = None
    pending_prompt = None  # (prompt_eval_ms, input_tokens, prompt_tps, cached)
    current_offset = 0.0  # router timestamp (seconds) captured from the proxy line

    # base datetime = file creation time (st_birthtime is creation time on Windows)
    base_dt = datetime.datetime.fromtimestamp(os.stat(log_path).st_birthtime)

    with open(log_path, "r", encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            m = RE_MODEL.search(line)
            if m:
                # a new request is starting; drop any stale pending state
                current_model = m.group(1)
                pending_prompt = None
                # anchor the offset to the router (proxy) timestamp, not the
                # child-server timestamp which can reset on model switches
                m_ts = RE_TS.match(line)
                current_offset = ts_to_seconds(m_ts) if m_ts else 0.0
                continue

            m = RE_PROMPT.search(line)
            if m:
                pending_prompt = (
                    m.group(1),  # prompt_eval_time_ms
                    m.group(2),  # input_tokens
                    m.group(3),  # prompt_tokens_per_second
                    m.group(4),  # cached_input_tokens
                )
                continue

            m = RE_EVAL.search(line)
            if m and pending_prompt is not None:
                prompt_eval_ms, input_tokens, prompt_tps, cached = pending_prompt
                offset = current_offset
                req_dt = base_dt + datetime.timedelta(seconds=offset)
                yield {
                    "model": current_model if current_model is not None else "",
                    "cached_input_tokens": cached,
                    "input_tokens": input_tokens,
                    "output_tokens": m.group(2),
                    "prompt_eval_time_ms": prompt_eval_ms,
                    "eval_time_ms": m.group(1),
                    "prompt_tokens_per_second": prompt_tps,
                    "output_tokens_per_second": m.group(3),
                    "datetime": req_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                }
                pending_prompt = None


def main():
    argv = sys.argv[1:]
    delete_log = "--delete" in argv
    args = [a for a in argv if a != "--delete"]

    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = args[0] if len(args) > 0 else os.path.join(script_dir, "raw_server.log")
    md_path = args[1] if len(args) > 1 else os.path.join(script_dir, "parsed_request_stats.md")

    if not os.path.isfile(log_path):
        print(f"[token_stats] ERROR: log file not found: {log_path}")
        return 1

    rows = list(parse(log_path))

    # write the header (and separator) only if the file does not exist yet or is empty
    need_header = (not os.path.exists(md_path)) or (os.path.getsize(md_path) == 0)

    with open(md_path, "a", newline="", encoding="utf-8") as f:
        if need_header:
            f.write("| " + " | ".join(HEADER) + " |\n")
            f.write("|" + "|".join(" --- " for _ in HEADER) + "|\n")
        for r in rows:
            f.write("| " + " | ".join(str(r[k]) for k in KEYS) + " |\n")

    print(f"[token_stats] parsed {len(rows)} request(s) from {os.path.basename(log_path)}")
    print(f"[token_stats] appended to {md_path}")

    if delete_log:
        # stamp the creation time to now first so that, if NTFS tunneling
        # restores a creation date when the server recreates the file, it is
        # approximately correct rather than a stale cached value
        set_creation_time_now(log_path)
        try:
            os.remove(log_path)
            print(f"[token_stats] deleted {log_path}")
        except OSError as e:
            print(f"[token_stats] WARNING: could not delete {log_path}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
