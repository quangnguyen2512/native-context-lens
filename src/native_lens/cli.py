"""CLI for native-context-lens: benchmark, replay-check, export-artifact, serve."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import uvicorn

from native_lens.artifacts import ArtifactRuntime
from native_lens.benchmark import (
    BenchmarkRunner,
    format_benchmark_json,
    format_benchmark_markdown,
)
from native_lens.engine import NativeContextEngine
from native_lens.vault import default_vault_dir, load_vault_into_engine


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="native-lens",
        description="Governed Context Engine, Markdown-vs-Native Benchmark & Artifact Workbench",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_bench = sub.add_parser("benchmark", help="Run Markdown-vs-Native head-to-head benchmark")
    p_bench.add_argument("--scenario", default=None, help="Optional single scenario_id")
    p_bench.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p_bench.add_argument("--out", default=None, help="Optional output file path")

    sub.add_parser("replay-check", help="Drop projections and verify deterministic event replay")

    p_exp = sub.add_parser("export-artifact", help="Export valid Native Document kind:artifact")
    p_exp.add_argument(
        "--view",
        choices=["compact_decision_table", "kanban_dependency_cards"],
        default="compact_decision_table",
    )
    p_exp.add_argument("--caller", default="founder")

    p_srv = sub.add_parser("serve", help="Launch interactive FastAPI workbench server")
    p_srv.add_argument("--host", default="127.0.0.1")
    p_srv.add_argument("--port", type=int, default=8790)

    args = parser.parse_args(argv)

    if args.command == "benchmark":
        runner = BenchmarkRunner(vault_dir=default_vault_dir())
        report = runner.run_all(scenario_id=args.scenario)
        text = (
            format_benchmark_json(report)
            if args.format == "json"
            else format_benchmark_markdown(report)
        )
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"Wrote benchmark report to {args.out}")
        else:
            print(text)
        return 0

    if args.command == "replay-check":
        engine = NativeContextEngine(":memory:")
        stats = load_vault_into_engine(engine)
        ver = engine.rebuild_projections()
        print(
            json.dumps(
                {
                    "vault_ingested": stats,
                    "replay_verification": ver.model_dump(),
                },
                indent=2,
            )
        )
        return 0 if (ver.deterministic_match and ver.chain_integrity_valid) else 1

    if args.command == "export-artifact":
        engine = NativeContextEngine(":memory:")
        load_vault_into_engine(engine)
        runtime = ArtifactRuntime(engine)
        rendered = runtime.render_view(args.view, caller=args.caller)
        print(rendered.document_export)
        return 0

    if args.command == "serve":
        uvicorn.run("native_lens.app:app", host=args.host, port=args.port, reload=False)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
