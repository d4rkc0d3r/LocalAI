#!/usr/bin/env python3
"""
Adds the cached token count to the per-request "prompt eval time" log line in
llama.cpp-latest/tools/server/server-context.cpp.

Idempotent: skips if already applied, warns if the target lines no longer match.
Line-ending independent (works with CRLF or LF, with or without BOM).
"""
import os
import sys


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(root, "llama.cpp-latest", "tools", "server", "server-context.cpp")

    if not os.path.isfile(target):
        print(f"[patch] ERROR: {target} not found")
        return 1

    with open(target, "rb") as f:
        data = f.read()

    has_bom = data[:3] == b"\xef\xbb\xbf"
    text = data[3:].decode("utf-8") if has_bom else data.decode("utf-8")

    # Detect original line ending
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(eol)

    # Exact old -> new line pairs (each must match exactly once).
    # Note: the C++ source contains a literal backslash-n inside the string,
    # so it is written as \\n here.
    pairs = [
        (
            '                "prompt eval time = %10.2f ms / %5d tokens (%8.2f ms per token, %8.2f tokens per second)\\n",',
            '                "prompt eval time = %10.2f ms / %5d tokens (%8.2f ms per token, %8.2f tokens per second, %5d cached)\\n",',
        ),
        (
            "                t_prompt_total, (int) stats.n_prompt_processed, t_prompt, n_prompt_second);",
            "                t_prompt_total, (int) stats.n_prompt_processed, t_prompt, n_prompt_second, (int) stats.n_prompt_cached);",
        ),
    ]

    # Idempotency: if the "new" format string is already present, we're done.
    if pairs[0][1] in lines:
        print("[patch] already applied, skipping")
        return 0

    for old, new in pairs:
        count = lines.count(old)
        if count != 1:
            print(f"[patch] WARNING: expected exactly 1 match, found {count} for line: {old}")
            print("[patch] WARNING: context mismatch after pull? Patch NOT applied.")
            return 1
        lines = [new if line == old else line for line in lines]

    out = eol.join(lines)
    with open(target, "wb") as f:
        if has_bom:
            f.write(b"\xef\xbb\xbf")
        f.write(out.encode("utf-8"))

    print("[patch] applied: cached tokens now logged per request")
    return 0


if __name__ == "__main__":
    sys.exit(main())
