#!/usr/bin/env python3
"""Build a prompt from local files and query a local llama.cpp server to summarize upstream changes."""

import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Summarize upstream llama.cpp changes via local LLM server")
    parser.add_argument("--server-url", required=True, help="Base URL of the llama.cpp server (no trailing /)")
    parser.add_argument("--model", required=True, help="Model name to use")
    parser.add_argument("--output", required=True, help="Path to write the summary output file")
    parser.add_argument("--dir", required=True, help="Directory containing the context files")
    args = parser.parse_args()

    server_url = args.server_url.rstrip("/")
    base_dir = Path(args.dir)

    # Files to include in the prompt context
    files = [
        base_dir / "changes_raw_commits.md",
        base_dir.parent / "README.md",
        base_dir.parent / "LaunchServer.bat",
        base_dir.parent / "models.ini",
    ]

    print(f"Files to include: {' | '.join(f.name for f in files)}")

    # Validate all files exist
    for f in files:
        if not f.exists():
            print(f"ERROR: missing file {f}", file=sys.stderr)
            sys.exit(1)

    # Load prompt text
    prompt_path = Path(__file__).resolve().parent / "prompt.txt"
    if not prompt_path.exists():
        print(f"ERROR: missing file {prompt_path}", file=sys.stderr)
        sys.exit(1)
    prompt_text = prompt_path.read_text(encoding="utf-8").strip()

    # Build prompt parts
    parts = [prompt_text]
    for f in files:
        content = f.read_text(encoding="utf-8")
        # Replace thinking tokens to avoid confusing the model
        content = content.replace("<think>", "<START_THINKING_TOKEN>").replace("</thinking>", "<END_TOKEN>")
        parts.append("")
        parts.append(f"===== FILE: {f.name} =====")
        parts.append(content)
    parts.append("")
    parts.append("===== END OF FILES =====")

    prompt_content = "\n".join(parts)
    print(f"Prompt size: {len(prompt_content) / 1024:.1f} KB")

    # Build request body
    body = {
        "model": args.model,
        "stream": False,
        "max_tokens": 16384,
        "messages": [
            {"role": "user", "content": prompt_content}
        ],
    }

    body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")

    # Send request
    url = f"{server_url}/v1/chat/completions"
    print(f"Sending request to {url} (may take a few minutes)...")

    req = urllib.request.Request(
        url,
        data=body_bytes,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"ERROR: request failed: {e}", file=sys.stderr)
        print(f"Is the server running with the {args.model} model loaded?", file=sys.stderr)
        sys.exit(1)

    answer = data["choices"][0]["message"]["content"]

    # Build output
    header = (
        f"# llama.cpp Changes Summary\n"
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Model: {args.model}\n"
        f"Source: changes_raw_commits.md\n"
        f"---\n\n"
    )

    output_path = Path(args.output)
    output_path.write_text(header + answer, encoding="utf-8")

    usage = data.get("usage", {})
    print(f"Done. Tokens: {usage.get('prompt_tokens', '?')} prompt / {usage.get('completion_tokens', '?')} completion")
    print(f"Written to {output_path}")


if __name__ == "__main__":
    main()
