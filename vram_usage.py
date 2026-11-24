
#!/usr/bin/env python3
"""Per-model VRAM usage for the Qwen3.8 variants.

For every model in MODELS this script:
  1. snapshots the current GPU memory (baseline),
  2. launches a llama-server (router mode, models.ini) the way
     token_stats/test_parser.py does and sends a dummy chat request
     ("What is 6 + 7?") which triggers the on-demand model load,
  3. waits for the result,
  4. snapshots the GPU memory again,
  5. prints "<model>: <x.x> GiB" (the delta between the two snapshots).

Every GPU snapshot is the sum of the UsageGB of ALL entries reported by the
PowerShell counter ("dedicated usage" + "shared usage").

When all models have been measured the server is shut down.

Usage:
    python vram_usage.py            # default Qwen3.8 list
    python vram_usage.py <filter>   # query /v1/models and keep only names
                                    # containing <filter> (case-insensitive)
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

# --- configuration ----------------------------------------------------------

# default models to measure, as defined in models.ini
MODELS = [
    "Qwen3.8-27B-medium",
    "Qwen3.8-27B-fast",
    "Qwen3.8-27B-vision",
]

PORT = 8321  # dedicated port for this script's own test server
BASE = f"http://127.0.0.1:{PORT}"

LIVE_PORT = 8000  # port used by LaunchServer.bat; abort if that's already up
LIVE_BASE = f"http://127.0.0.1:{LIVE_PORT}"

SERVER_EXE = "llama.cpp-CUDA\\llama-server.exe"
LOG_DIR = "token_stats"
LOG_NAME = "raw_vram_test_server.log"
DUMMY_PROMPT = "What is 6 + 7? return only the answer number, no formatting."

START_TIMEOUT = 10   # seconds to wait for the HTTP port to come up
REQUEST_TIMEOUT = 60  # first call loads the model


# --- GPU memory snapshot -----------------------------------------------------

def ps_vram_total():
    """Query GPU memory via PowerShell and return the sum of the UsageGB of
    ALL entries (dedicated + shared)."""
    ps = r"""
$paths = @(
    '\GPU Adapter Memory(*)\Dedicated Usage',
    '\GPU Adapter Memory(*)\Shared Usage'
)

$samples = Get-Counter -Counter $paths -ErrorAction Stop

$samples.CounterSamples |
    Group-Object { ($_.Path -split '\\')[-1] } |
    ForEach-Object {
        $total = ($_.Group | Measure-Object CookedValue -Sum).Sum
        [PSCustomObject]@{
            MemoryType = $_.Name
            UsageGB = [math]::Round($total / 1GB, 3)
        }
    } | ConvertTo-Json
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "powershell failed")
    entries = json.loads(result.stdout)
    return sum(float(e["UsageGB"]) for e in entries)


# --- server helpers (mirrors token_stats/test_parser.py) ---------------------

def wait_for_server(base, timeout):
    """Poll the server until the HTTP port answers. The model itself is only
    loaded on the first chat call."""
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


def chat(model, messages, timeout=REQUEST_TIMEOUT):
    """Send a chat completion and return the assistant text (content, or
    reasoning_content for reasoning models)."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "max_tokens": 64,
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


def start_server(root, log_path):
    """Launch llama-server in router mode. Output is redirected to a file so a
    failed start can be inspected; writing to a file (not a pipe) avoids the
    'unread pipe fills up and deadlocks' problem."""
    out_file = open(log_path, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        [
            SERVER_EXE,
            "--port", str(PORT),
            "--models-preset", "models.ini",
            "--timeout", "600",
            "--models-max", "1",
            "--parallel", "1",
            "--log-colors", "off",
            "--log-file", log_path,
        ],
        cwd=root,
        stdout=out_file,
        stderr=subprocess.STDOUT,
    )
    return proc, out_file


def kill_server(proc, out_file=None):
    """Terminate the server and its process tree."""
    if proc is None:
        return
    try:
        # Force-kill the FULL tree while the parent is still alive; a plain
        # kill() would orphan the still-running llama-server child.
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
    try:
        if proc.poll() is None:
            proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=10)
    except Exception:
        pass
    if out_file is not None:
        try:
            out_file.flush()
            out_file.close()
        except Exception:
            pass


# --- main --------------------------------------------------------------------

def fetch_models(base, timeout=START_TIMEOUT):
    """Query the server's /v1/models endpoint and return the list of model
    names (router mode)."""
    with urllib.request.urlopen(base + "/v1/models", timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    return [m["id"] for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]


def resolve_models(root, log_path, filter_text):
    """Return the list of models to measure.

    With no filter, use the hardcoded default MODELS list. With a filter, start
    a server, read /v1/models, keep only names containing the filter
    (case-insensitive), then shut the server down."""
    if not filter_text:
        return list(MODELS)

    proc = None
    out_file = None
    try:
        proc, out_file = start_server(root, log_path)
        if not wait_for_server(BASE, timeout=START_TIMEOUT):
            print(f"[vram] ERROR: server did not start in time (see {log_path})")
            return []
        try:
            names = fetch_models(BASE)
        except Exception as e:
            print(f"[vram] ERROR: could not query /v1/models: {e}")
            return []
        needle = filter_text.lower()
        return [n for n in names if needle in n.lower()]
    finally:
        kill_server(proc, out_file)


def preflight_check():
    """Abort if the live server (LaunchServer.bat, port 8000) is already up,
    since its loaded model would pollute the VRAM measurements."""
    try:
        urllib.request.urlopen(LIVE_BASE + "/v1/models", timeout=1)
        print(f"[vram] ERROR: the live server is already running on port "
              f"{LIVE_PORT}, aborting")
        return False
    except urllib.error.URLError:
        return True
    except Exception:
        return True


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(root, LOG_DIR, LOG_NAME)
    os.makedirs(os.path.join(root, LOG_DIR), exist_ok=True)

    filter_text = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else ""

    if not preflight_check():
        return 1

    models = resolve_models(root, log_path, filter_text)
    if not models:
        print("[vram] No models selected (check the filter)")
        return 1
    print(f"[vram] measuring {len(models)} model(s): {', '.join(models)}")

    proc = None
    out_file = None
    results = {}
    baselines = []
    request_times = []

    try:
        for model in models:
            # 1) baseline before loading this model
            try:
                before = ps_vram_total()
            except Exception as e:
                print(f"[vram] ERROR: baseline snapshot failed for {model}: {e}")
                continue
            baselines.append(before)

            # 2) start a fresh server for this model
            try:
                proc, out_file = start_server(root, log_path)
            except Exception as e:
                print(f"[vram] ERROR: could not start server for {model}: {e}")
                continue

            if not wait_for_server(BASE, timeout=START_TIMEOUT):
                print(f"[vram] ERROR: server for {model} did not start in time "
                      f"(see {log_path})")
                kill_server(proc, out_file)
                proc, out_file = None, None
                continue

            # 3) the first chat call triggers the on-demand model load
            try:
                t0 = time.time()
                chat(model, [{"role": "user", "content": DUMMY_PROMPT}])
                request_times.append(time.time() - t0)
            except Exception as e:
                print(f"[vram] ERROR: dummy request failed for {model}: {e}")

            # 4) snapshot again once the model is loaded
            time.sleep(1)  # let it settle
            after = None
            try:
                after = ps_vram_total()
            except Exception as e:
                print(f"[vram] ERROR: after snapshot failed for {model}: {e}")

            # shut this model's server down before the next one
            kill_server(proc, out_file)
            proc, out_file = None, None
            time.sleep(1)  # let the GPU release memory

            # 5) report
            if after is None:
                print(f"{model}: n/a GiB")
                continue
            delta = after - before
            results[model] = delta
            print(f"{model}: {delta:.2f} GiB")
    finally:
        # when we're done, make sure nothing is left running
        if proc is not None:
            kill_server(proc, out_file)

    if baselines:
        print(f"baseline usage: {sum(baselines) / len(baselines):.2f} GiB")
    if request_times:
        print(f"avg request time: {sum(request_times) / len(request_times):.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
