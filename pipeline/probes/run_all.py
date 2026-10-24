"""Run every source probe and return a failing status if any probe fails."""
import importlib
import pkgutil
import sys
import traceback

import pipeline.probes as probes
from pipeline.security import redact


def main():
    failed = []
    for module in sorted(n.name for n in pkgutil.iter_modules(probes.__path__) if n.name.startswith("probe_")):
        print(f"== {module}", flush=True)
        try:
            importlib.import_module(f"pipeline.probes.{module}")
        except Exception as error:
            failed.append(module)
            print("FAILED:", redact("".join(traceback.format_exception_only(error)).strip())[:600])
    print("\nfailed:", failed or "none")
    return int(bool(failed))


if __name__ == "__main__":
    sys.exit(main())
