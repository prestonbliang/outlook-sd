"""make probe: run every probe; report failures with their message instead of stopping."""
import importlib
import pkgutil
import traceback

import pipeline.probes as probes

if __name__ == "__main__":
    failed = []
    for m in sorted(n.name for n in pkgutil.iter_modules(probes.__path__) if n.name.startswith("probe_")):
        print(f"== {m}", flush=True)
        try:
            importlib.import_module(f"pipeline.probes.{m}")
        except Exception as e:  # report and continue (rule 1: report URL, status, sample)
            failed.append(m)
            print("FAILED:", "".join(traceback.format_exception_only(e)).strip()[:600])
    print("\nfailed:", failed or "none")
