from __future__ import annotations

from api.app.runtime_checks import run_runtime_checks, summarize_runtime_checks



def main() -> None:
    checks = run_runtime_checks()
    summary = summarize_runtime_checks(checks)
    for check in summary["checks"]:
        required = "required" if check["required"] else "optional"
        print(f"[{check['status'].upper()}] {check['name']} ({required}) - {check['detail']}")
    if summary["error_count"]:
        raise SystemExit(1)
    print("Runtime preflight passed.")


if __name__ == "__main__":
    main()
