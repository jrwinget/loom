"""export the openapi schema deterministically.

feeds the frontend type generation (`pnpm generate:api`) and the CI
drift check: the schema and the generated types are checked in, and
CI fails when a backend change lands without regenerating them.
sorted keys make the output stable across runs, which is what lets
`git diff --exit-code` be the check.

usage: ``python -m loom.scripts.export_openapi [--out PATH]``
"""

import argparse
import json
import sys
from pathlib import Path


def render_schema() -> str:
    """render the openapi document as stable, sorted json."""
    # settings validation happens in the lifespan, not create_app, so
    # no env is needed here (same property the route-contract test
    # relies on)
    from loom.main import create_app

    schema = create_app().openapi()
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write to this path instead of stdout",
    )
    args = parser.parse_args()

    rendered = render_schema()
    if args.out is None:
        sys.stdout.write(rendered)
    else:
        args.out.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
