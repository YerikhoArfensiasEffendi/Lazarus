"""Command-line interface for Lazarus — The Underground Office."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

import uvicorn

from lazarus import __version__
from lazarus.constitution import LazarusConstitution
from lazarus.memory import KnowledgeStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lazarus",
        description="Lazarus (The Underground Office) — Loyal, honest, adaptive assistant CLI.",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Optional path to SQLite database (defaults to LAZARUS_DB_PATH or data/lazarus.db).",
    )
    parser.add_argument("--version", action="version", version=f"lazarus {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show Lazarus health, constitution summary, and stats.")
    subparsers.add_parser("constitution", help="Print Lazarus directives and non-harm charter.")

    check_p = subparsers.add_parser("check", help="Evaluate an action against safety directives.")
    check_p.add_argument("action", help="Proposed command or action description.")

    learn_p = subparsers.add_parser("learn", help="Record a verified learning in SQLite memory.")
    learn_p.add_argument("--topic", required=True, help="Knowledge topic.")
    learn_p.add_argument("--content", required=True, help="Verified insight or details.")
    learn_p.add_argument("--source", default="direct-observation", help="Source of truth.")
    learn_p.add_argument("--tags", default="", help="Comma-separated tags.")

    recall_p = subparsers.add_parser("recall", help="Search stored learnings.")
    recall_p.add_argument("query", nargs="?", default="", help="Optional search text.")
    recall_p.add_argument("--limit", type=int, default=20, help="Maximum records to return.")

    report_p = subparsers.add_parser("report", help="Log a transparent status report.")
    report_p.add_argument("--title", required=True, help="Report title.")
    report_p.add_argument("--summary", required=True, help="Report findings.")
    report_p.add_argument("--category", default="general", help="Report category.")
    report_p.add_argument(
        "--confidence", type=float, default=0.85, help="Confidence score between 0.0 and 1.0."
    )
    report_p.add_argument(
        "--gaps", default="", help="Explicit unknowns, assumptions, or unverified parts."
    )

    reports_p = subparsers.add_parser("reports", help="List recent honest reports.")
    reports_p.add_argument("--limit", type=int, default=20, help="Maximum reports to return.")

    adapt_p = subparsers.add_parser("adapt", help="Record an adaptation to a new environment/tool.")
    adapt_p.add_argument("--trigger", required=True, help="What changed or triggered adaptation.")
    adapt_p.add_argument("--change", required=True, help="How Lazarus adapted.")
    adapt_p.add_argument("--rationale", required=True, help="Why this adaptation improves results.")

    adaptations_p = subparsers.add_parser("adaptations", help="List recorded adaptations.")
    adaptations_p.add_argument("--limit", type=int, default=20, help="Maximum items to return.")

    serve_p = subparsers.add_parser("serve", help="Run the Lazarus FastAPI HTTP server.")
    serve_p.add_argument("--host", default="127.0.0.1", help="Bind host.")
    serve_p.add_argument("--port", type=int, default=8000, help="Bind port.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "constitution":
        print(json.dumps(LazarusConstitution.to_dict(), indent=2))
        return 0

    if args.command == "check":
        result = LazarusConstitution.evaluate_action(args.action)
        print(json.dumps(asdict(result), indent=2))
        return 0 if result.allowed else 2

    if args.command == "serve":
        uvicorn.run("lazarus.api:app", host=args.host, port=args.port, reload=False)
        return 0

    store = KnowledgeStore(db_path=args.db)

    if args.command == "status":
        payload = {
            "service": LazarusConstitution.name,
            "version": __version__,
            "db_path": str(store.db_path),
            "directives_count": len(LazarusConstitution.directives),
            "stats": store.stats(),
        }
        print(json.dumps(payload, indent=2))
        return 0

    if args.command == "learn":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        entry = store.learn(
            topic=args.topic, content=args.content, source=args.source, tags=tags
        )
        print(json.dumps(entry.to_dict(), indent=2))
        return 0

    if args.command == "recall":
        entries = [e.to_dict() for e in store.recall(query=args.query, limit=args.limit)]
        print(json.dumps({"query": args.query, "count": len(entries), "items": entries}, indent=2))
        return 0

    if args.command == "report":
        entry = store.log_report(
            title=args.title,
            summary=args.summary,
            category=args.category,
            confidence=args.confidence,
            honest_gaps=args.gaps,
        )
        print(json.dumps(entry.to_dict(), indent=2))
        return 0

    if args.command == "reports":
        entries = [e.to_dict() for e in store.list_reports(limit=args.limit)]
        print(json.dumps({"count": len(entries), "items": entries}, indent=2))
        return 0

    if args.command == "adapt":
        entry = store.record_adaptation(
            trigger=args.trigger, change=args.change, rationale=args.rationale
        )
        print(json.dumps(entry.to_dict(), indent=2))
        return 0

    if args.command == "adaptations":
        entries = [e.to_dict() for e in store.list_adaptations(limit=args.limit)]
        print(json.dumps({"count": len(entries), "items": entries}, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
