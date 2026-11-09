"""CLI: python -m hello_contract compile|check-breaking"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .compile import find_breaking_changes, load_yaml, write_outputs


def cmd_compile(args: argparse.Namespace) -> int:
    odcs = load_yaml(Path(args.odcs))
    odps = load_yaml(Path(args.odps)) if args.odps else None
    out_dir = Path(args.out)
    written = write_outputs(out_dir, odcs, odps)
    print(f"Compiled {len(written)} artifact(s) to {out_dir.resolve()}")
    for path in written:
        print(f"  - {path.name}")
    return 0


def cmd_check_breaking(args: argparse.Namespace) -> int:
    before = load_yaml(Path(args.before))
    after = load_yaml(Path(args.after))
    breaks = find_breaking_changes(before, after)
    if not breaks:
        print("No breaking changes detected.")
        return 0
    print("Breaking changes detected:")
    for item in breaks:
        print(f"  - {item}")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hello_contract",
        description="Pactmill lab: ODCS/ODPS → JSON Schema, expectations, MCP stub",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    compile_p = sub.add_parser("compile", help="Compile ODCS/ODPS to artifacts")
    compile_p.add_argument("--odcs", required=True, help="Path to ODCS YAML")
    compile_p.add_argument("--odps", help="Path to ODPS YAML")
    compile_p.add_argument("--out", required=True, help="Output directory")
    compile_p.set_defaults(func=cmd_compile)

    break_p = sub.add_parser(
        "check-breaking", help="Detect breaking ODCS schema changes"
    )
    break_p.add_argument("--before", required=True, help="Baseline ODCS YAML")
    break_p.add_argument("--after", required=True, help="Candidate ODCS YAML")
    break_p.set_defaults(func=cmd_check_breaking)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
