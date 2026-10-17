#!/usr/bin/env python3
"""Paired, prebuilt Horizon full-client time-to-title-ready benchmark.

Build both revisions independently first; each invocation starts the real Vulkan
client, waits for `status.screen == title` and a populated renderer, then quits.
Do not compare different build profiles or treat the world loader as startup.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import random
import re
import shutil
import socket
import statistics
import subprocess
import tempfile
import time

from profile_client_startup import RESOURCE_FILES, cpu_pressure, digest, summary


def paired_uncertainty(deltas, replicates=20000):
    """Deterministic pair-resampling percentile intervals, no independence claim across runs."""
    rng = random.Random(20261017)
    boot_means = []
    boot_medians = []
    for _ in range(replicates):
        draw = rng.choices(deltas, k=len(deltas))
        boot_means.append(statistics.mean(draw))
        boot_medians.append(statistics.median(draw))
    boot_means.sort()
    boot_medians.sort()
    lower, upper = int(.025 * replicates), int(.975 * replicates)
    return {
        "method": "paired percentile bootstrap; iid-pair assumption; exploratory",
        "seed": 20261017,
        "resamples": replicates,
        "mean_95pct_ci_ms": [round(boot_means[lower], 3), round(boot_means[upper], 3)],
        "median_95pct_ci_ms": [round(boot_medians[lower], 3), round(boot_medians[upper], 3)],
        "fraction_negative": sum(value < 0 for value in deltas) / len(deltas),
    }


def process_cpu_ms(pid):
    # proc stat fields 14 and 15 follow the parenthesized comm field.
    text = Path(f"/proc/{pid}/stat").read_text()
    fields = text[text.rfind(")") + 2:].split()
    return 1000 * (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")


def process_switches(pid):
    lines = Path(f"/proc/{pid}/status").read_text().splitlines()
    return {
        key: int(value.strip())
        for line in lines
        if (key := line.partition(":")[0]) in
        ("voluntary_ctxt_switches", "nonvoluntary_ctxt_switches")
        for value in [line.partition(":")[2]]
    }


def logged_startup_stages(output):
    stages = {}
    for name in ("assets", "facts", "items", "biomes+env", "pack tables",
                 "atlas", "collision+motion"):
        match = re.search(r"^load " + re.escape(name) + r":\s+([0-9.]+)s",
                          output, flags=re.MULTILINE)
        if match:
            stages[name] = round(float(match.group(1)) * 1000, 1)
    return stages


def concurrent_compilers():
    count = 0
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            try:
                if (entry / "comm").read_text().strip() in ("cargo", "rustc"):
                    count += 1
            except (OSError, PermissionError):
                pass
    return count


def gpu_pressure():
    if not shutil.which("nvidia-smi"):
        return None
    try:
        report = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,utilization.memory,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3, check=True)
        return report.stdout.strip().splitlines()
    except (OSError, subprocess.SubprocessError):
        return None


def control(path, request, timeout=0.5):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(timeout)
        conn.connect(str(path))
        conn.sendall((request + "\n").encode())
        response = b""
        while not response.endswith(b"\n"):
            part = conn.recv(65536)
            if not part:
                raise RuntimeError("control disconnected")
            response += part
    return json.loads(response)


def ready_sample(binary, resources, affinity, timeout, root, label, iteration):
    with tempfile.TemporaryDirectory(prefix=f"{label}-{iteration}-", dir=root) as temp:
        workdir = Path(temp)
        sock = workdir / "control.sock"
        log_path = workdir / "client.log"
        command = [str(binary), "--resources", str(resources), "--offscreen",
                   "--no-pause", "--control-socket", str(sock)]
        env = dict(os.environ, HORIZON_NO_AUDIO="1", HORIZON_MENU_STYLE="classic")
        with log_path.open("w+") as log:
            start = time.perf_counter_ns()
            proc = subprocess.Popen(command, cwd=workdir, env=env,
                                    stdout=log, stderr=subprocess.STDOUT,
                                    preexec_fn=(lambda: os.sched_setaffinity(0, affinity))
                                    if affinity else None)
            status = None
            elapsed_ms = None
            cpu_ms = None
            switches = None
            failure = None
            try:
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        raise RuntimeError(f"client exited before ready: {proc.returncode}")
                    try:
                        answer = control(sock, "status", timeout=0.4)
                        if (answer.get("screen") == "title" and answer.get("renderer")):
                            elapsed_ms = (time.perf_counter_ns() - start) / 1e6
                            cpu_ms = process_cpu_ms(proc.pid)
                            switches = process_switches(proc.pid)
                            status = answer
                            break
                    except (OSError, ValueError, RuntimeError):
                        pass
                    time.sleep(0.025)
                if status is None:
                    raise TimeoutError(f"title and renderer not ready within {timeout}s")
            except Exception as exc:
                failure = exc
            finally:
                if proc.poll() is None:
                    try:
                        control(sock, "quit", timeout=2)
                    except (OSError, ValueError, RuntimeError):
                        pass
                try:
                    proc.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                log.flush()
                log.seek(0)
                output = log.read()
        if failure is not None:
            raise RuntimeError(f"{label} failed: {failure}; log tail: {output[-1800:]}")
        match = re.search(r"first frame after\s+(\d+)\s+ms", output)
        return {
            "wall_ready_ms": round(elapsed_ms, 3),
            "cpu_ready_ms": round(cpu_ms, 3),
            "first_frame_logged_ms": int(match.group(1)) if match else None,
            "switches_at_ready": switches,
            "renderer": status["renderer"],
            "client_log_cumulative_stage_ms": logged_startup_stages(output),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--baseline-binary", type=Path, required=True)
    parser.add_argument("--optimized-binary", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=12)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=40)
    parser.add_argument("--pause-ms", type=int, default=250)
    parser.add_argument("--affinity", help="Optional Linux logical CPU list e.g. 2,3")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.runs <= 0 or args.warmups < 0 or args.pause_ms < 0:
        parser.error("invalid run count, warmups or pause")
    affinity = None
    if args.affinity:
        try:
            affinity = {int(s) for s in args.affinity.split(",")}
        except ValueError:
            parser.error("affinity must list integer CPUs")
        if not affinity or not affinity.issubset(os.sched_getaffinity(0)):
            parser.error("affinity must be a subset of allowed CPUs")
    resources = args.resources.resolve(strict=True)
    binaries = {"baseline": args.baseline_binary.resolve(strict=True),
                "optimized": args.optimized_binary.resolve(strict=True)}
    for file in RESOURCE_FILES:
        if not (resources / file).is_file():
            parser.error(f"missing {file} in resources")
    result = {
        "scope": "actual Horizon client process start to status title + renderer (offscreen)",
        "start_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_model": next((line.split(":", 1)[1].strip() for line in
                           Path("/proc/cpuinfo").read_text().splitlines()
                           if line.startswith("model name")), None),
        "resources": str(resources),
        "resource_sha256": {file: digest(resources / file) for file in RESOURCE_FILES},
        "binary_sha256": {name: digest(path) for name, path in binaries.items()},
        "binaries": {name: str(path) for name, path in binaries.items()},
        "configuration": "--offscreen --no-pause --control-socket, fresh empty cwd, HORIZON_NO_AUDIO=1, HORIZON_MENU_STYLE=classic",
        "gpu_note": "Both clients render offscreen with identical hardware/driver; per-run renderer metadata saved",
        "poll_interval_ms": 25,
        "affinity": sorted(affinity) if affinity else None,
        "warmups_per_binary": args.warmups,
        "runs_per_binary": args.runs,
        "pause_ms": args.pause_ms,
        "timeout_s": args.timeout,
        "system_load_before": list(os.getloadavg()),
        "pairs": [],
    }
    samples = {label: [] for label in binaries}
    cpus = {label: [] for label in binaries}
    frame_logs = {label: [] for label in binaries}
    with tempfile.TemporaryDirectory(prefix="horizon-title-bench-") as temp:
        for i in range(args.warmups + args.runs):
            order = list(binaries) if i % 2 == 0 else list(reversed(binaries))
            pair = {"order": order, "load_before": list(os.getloadavg()),
                    "pressure_before": cpu_pressure(),
                    "compilers_before": concurrent_compilers(),
                    "gpu_before": gpu_pressure(), "measurements": {}}
            for label in order:
                try:
                    item = ready_sample(binaries[label], resources, affinity, args.timeout,
                                        temp, label, i)
                except Exception as exc:
                    result["failed_run"] = {"iteration": i, "label": label, "error": str(exc)}
                    result["end_utc"] = datetime.now(timezone.utc).isoformat()
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(json.dumps(result, indent=2) + "\n")
                    raise
                if i >= args.warmups:
                    pair["measurements"][label] = item
                    samples[label].append(item["wall_ready_ms"])
                    cpus[label].append(item["cpu_ready_ms"])
                    if item["first_frame_logged_ms"] is not None:
                        frame_logs[label].append(item["first_frame_logged_ms"])
            if i >= args.warmups:
                pair["load_after"] = list(os.getloadavg())
                pair["pressure_after"] = cpu_pressure()
                pair["compilers_after"] = concurrent_compilers()
                pair["gpu_after"] = gpu_pressure()
                result["pairs"].append(pair)
            if args.pause_ms:
                time.sleep(args.pause_ms / 1000)
    result["results_wall_ms"] = {name: summary(values) for name, values in samples.items()}
    stable_renderer_fields = ("backend", "device_type", "driver", "gpu", "present_mode", "size", "vendor")
    renderers = {
        name: {json.dumps({key: pair["measurements"][name]["renderer"].get(key)
                           for key in stable_renderer_fields}, sort_keys=True)
               for pair in result["pairs"]}
        for name in binaries
    }
    if len(renderers["baseline"] | renderers["optimized"]) != 1:
        raise RuntimeError("renderer identity/backend changed across paired startup samples")
    result["results_cpu_ms"] = {name: summary(values) for name, values in cpus.items()}
    result["logged_first_frame_ms"] = {name: summary(values) if values else None
                                       for name, values in frame_logs.items()}
    result["paired_wall_delta_ms"] = summary([a-b for a,b in zip(samples["optimized"], samples["baseline"])])
    result["paired_cpu_delta_ms"] = summary([a-b for a,b in zip(cpus["optimized"], cpus["baseline"])])
    result["uncertainty_wall"] = paired_uncertainty([
        a - b for a, b in zip(samples["optimized"], samples["baseline"])
    ])
    result["uncertainty_cpu"] = paired_uncertainty([
        a - b for a, b in zip(cpus["optimized"], cpus["baseline"])
    ])
    result["system_load_after"] = list(os.getloadavg())
    result["end_utc"] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"wall": result["results_wall_ms"],
                      "cpu": result["results_cpu_ms"],
                      "paired_wall": result["paired_wall_delta_ms"],
                      "paired_cpu": result["paired_cpu_delta_ms"]}, indent=2))


if __name__ == "__main__":
    main()
