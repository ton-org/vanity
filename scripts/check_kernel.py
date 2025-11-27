#!/usr/bin/env python3
"""
Lightweight kernel render sanity for CI.
- Stubs pyopencl so import works without OpenCL.
- Builds a basic kernel config (prefix/suffix empty) and renders kernel.cl.
- Fails if any template placeholders remain.
"""

import base64
import sys
import types
from pathlib import Path


def main() -> int:
    sys.modules["pyopencl"] = types.SimpleNamespace()
    root = Path(__file__).resolve().parent.parent / "src"
    sys.path.insert(0, str(root))

    try:
        import generator  # type: ignore
    except Exception as e:  # pragma: no cover - CI guard
        print(f"Import failed: {e}", file=sys.stderr)
        return 1

    owner = "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c"
    owner_raw = base64.urlsafe_b64decode(owner + "==")
    cli = generator.CliConfig(
        owner=owner,
        start=None,
        end=None,
        masterchain=False,
        non_bounceable=False,
        testnet=False,
        case_sensitive=True,
        only_one=True,
    )

    cfg, _ = generator.build_kernel_config(cli, owner_raw)
    src = generator.render_kernel(cfg)

    import re

    if re.search(r"<<[A-Z0-9_]+>>", src):
        print("Kernel render left unresolved placeholders", file=sys.stderr)
        return 1

    print("kernel render OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
