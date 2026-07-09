# Sage Santomenna 2026
# memory growth tracer, enabled by the "traceMemory" setting in in_maestro_settings.toml
# #writes diffs to a log in files/outputs

import os
from os.path import join
import threading
import time
import tracemalloc
from datetime import datetime

diagnostic_counters_fn = None


def set_diagnostic_counters_fn(fn) -> None:
    # register a callable returning {label: count} to be logged with snapshot for recording more info
    global diagnostic_counters_fn
    diagnostic_counters_fn = fn


def trace_loop(log_path, interval_seconds):
    previous = tracemalloc.take_snapshot()
    start_time = datetime.now()
    while True:
        time.sleep(interval_seconds)
        snapshot = tracemalloc.take_snapshot()
        diff = snapshot.compare_to(previous, "lineno")
        previous = snapshot

        current, peak = tracemalloc.get_traced_memory()
        with open(log_path, "a") as f:
            elapsed = (datetime.now() - start_time).total_seconds()
            
            el_h = int(elapsed//3600)
            r_el = elapsed-el_h*3600
            el_m = int(r_el//60)  
            r_el -= el_m * 60
            el_s = r_el
            elapsed_str = f"{el_h}h{el_m}m{el_s:.0f}s"
            
            f.write(f"\n=== {datetime.now().isoformat()} ({elapsed_str}) ===\n")
            f.write(f"tracemalloc current={current / 1e9:.3f}GB peak={peak / 1e9:.3f}GB\n")

            if diagnostic_counters_fn is not None:
                try:
                    counters = diagnostic_counters_fn()
                    for label, value in counters.items():
                        f.write(f"  counter: {label} = {value}\n")
                except Exception as e:
                    f.write(f"  counter collection failed: {e!r}\n")

            f.write("Top growing allocation sites:\n")
            for stat in diff[:25]:
                f.write(f"  {stat}\n")


def start_memory_trace(maestro_dir: str, interval_seconds: int = 180) -> None:
    trace_dir = join(maestro_dir, "files", "outputs", "memory_traces")
    os.makedirs(trace_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    log_path = join(trace_dir, f"trace_{timestamp}.log")

    tracemalloc.start(25)

    thread = threading.Thread(target=trace_loop, args=(log_path, interval_seconds), daemon=True, name="MemoryTraceThread")
    thread.start()
