"""Probe the read-only native competition catalog against the live game.

Measures, without any write authorization, what ``tools.competition_catalog``
costs to build:

* how many native competition rows the pointer table holds,
* how long a cold scan takes versus a warm rebuild (reused while the table token
  matches and the five-second freshness window is open),
* memory reads / bytes issued through the borrowed reader,
* the reputation distribution and the standings-reason distribution.

Read metrics are explicitly reader-only: the warmed ``DatabaseIndex`` owns a
separate reader, so these counters do not represent total catalog read cost.

The probe never writes memory, never installs a hook and never touches a save or
an account: it borrows the normal game read lease (``borrow_game_reader``) and
only reads through the repo's own ``Reader``/``DatabaseIndex`` plumbing.

Usage (from the repository root)::

    python scripts/probe_competition_catalog.py
    python scripts/probe_competition_catalog.py --state-file state.json
    python scripts/probe_competition_catalog.py --no-game
    python scripts/probe_competition_catalog.py --label before --report-path before.json
    python scripts/probe_competition_catalog.py --full-catalog --report-path full.json

``--state-file`` takes a saved ``GET /api/state`` JSON body (or its ``output``
object) so the standings-reason distribution can be computed for a real save.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

_UNSUPPORTED_PROVIDER_REPORT = {
    "selection_provider": {
        "supported": False,
        "status": "unsupported",
        "reason": "No verified source exposes loaded Playable/View-Only competitions.",
    },
    "hierarchy_provider": {
        "supported": False,
        "status": "unsupported",
        "reason": "No verified parent-child competition hierarchy source is exposed.",
    },
}

from tools.competition_catalog import (  # noqa: E402  - after the path bootstrap
    STANDINGS_REASON_ORDER,
    build_league_catalog,
    LEAGUE_CATALOG_SOURCE_NATIVE,
    last_league_catalog_metrics,
    scan_native_competitions,
    unavailable_league_catalog,
)


def _load_state_output(path: Path | None) -> dict[str, Any]:
    """Return the ``output`` object of a saved state payload, or ``{}``."""
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("state file must contain a JSON object")
    output = payload.get("output")
    return dict(output) if isinstance(output, dict) else dict(payload)


def _read_metrics(reader: Any) -> dict[str, Any]:
    metrics = getattr(reader, "read_metrics", None)
    if not callable(metrics):
        return {}
    try:
        return dict(metrics() or {})
    except (OSError, RuntimeError, TypeError, ValueError):
        return {}


def _delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    keys = set(before) | set(after)
    out: dict[str, Any] = {}
    for key in sorted(keys):
        try:
            out[key] = int(after.get(key) or 0) - int(before.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return out


def _distribution(competitions: list[dict[str, Any]]) -> dict[str, Any]:
    reasons = Counter(
        str(item.get("standings_reason") or "native")
        for item in competitions
    )
    return {
        "count": len(competitions),
        "standings_available": sum(
            1 for item in competitions if item.get("standings_available")
        ),
        "standings_source": dict(Counter(
            str(item.get("standings_source")) for item in competitions
        )),
        "reasons": {
            code: reasons.get(code, 0)
            for code in ("native", *STANDINGS_REASON_ORDER)
        },
        "reasons_unlisted": {
            code: count for code, count in reasons.items()
            if code not in ("native", *STANDINGS_REASON_ORDER)
        },
    }


def _reputation_distribution(rows: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    values = [int(row.get("reputation") or 0) for row in rows]
    buckets = Counter(
        "0" if value == 0 else
        "1-9" if value < 10 else
        "10-19" if value < 20 else
        "20+" for value in values
    )
    return {
        "min": min(values) if values else 0,
        "max": max(values) if values else 0,
        "nonzero": sum(1 for value in values if value),
        "buckets": dict(buckets),
    }


def _safe_catalog_entries(competitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only the public competition id, names, and reputation."""
    return [
        {
            key: item.get(key)
            for key in ("competition_id", "name", "short_name", "reputation")
        }
        for item in competitions
    ]


def probe_live(
    output: dict[str, Any], *, limit: int, full_catalog: bool = False,
) -> dict[str, Any]:
    """Borrow the read lease and measure one cold scan plus one warm rebuild."""
    from tools.game_session import borrow_game_reader

    result: dict[str, Any] = {"mode": "live", "ok": False}
    result["reader_metrics_scope"] = "borrowed_reader_only"
    with borrow_game_reader() as reader:
        result["process_path"] = str(getattr(reader, "process_path", "") or "")
        layout = getattr(reader, "layout", None)
        result["game_layout"] = str(getattr(layout, "display_name", "") or "")
        result["layout_key"] = str(getattr(layout, "key", "") or "")
        result["game_identity"] = {
            "layout_key": result["layout_key"],
            "display_name": result["game_layout"],
            "distribution": str(getattr(layout, "distribution", "") or ""),
            "module_name": str(getattr(layout, "module_name", "") or ""),
            # This is the active GameLayout profile value; the probe does not
            # hash or inspect executable files.
            "executable_sha256": str(
                getattr(layout, "executable_sha256", "") or "",
            ) or None,
        }
        # Without a state file there is no ``game_layout`` in ``output``, so the
        # published field would read "" even though a layout was detected.  Use
        # the live layout key so the probe exercises the realistic payload.
        has_state = bool(output)
        output = dict(output)
        if not output.get("game_layout") and result["layout_key"]:
            output["game_layout"] = result["layout_key"]
        before = _read_metrics(reader)
        started = time.perf_counter()
        rows = scan_native_competitions(reader)
        cold_ms = (time.perf_counter() - started) * 1000.0
        after = _read_metrics(reader)
        result["rows"] = len(rows)
        result["cold_scan_ms"] = round(cold_ms, 1)
        result["reader_only_cold_reads"] = _delta(before, after)
        started = time.perf_counter()
        again = scan_native_competitions(reader)
        result["warm_scan_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
        result["warm_rows"] = len(again)
        result["reputation"] = _reputation_distribution(rows)
        started = time.perf_counter()
        standings = None
        # Only a loaded state carries the season results that standings need;
        # calling it on a synthetic output would resolve an account scope that a
        # bare probe has no right to touch.
        if has_state:
            from tools.league_standings import public_league_standings

            standings = public_league_standings(dict(output))
        result["standings_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
        started = time.perf_counter()
        catalog = build_league_catalog(
            output, scope_id="probe", standings=standings, reader=reader, force=True,
        )
        result["catalog_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
        # Refresh-path cost: exactly what a state refresh pays once the scan is
        # cached.  This is the number that matters for the hot path.
        before_refresh = _read_metrics(reader)
        started = time.perf_counter()
        refresh = build_league_catalog(
            output, scope_id="probe", standings=standings, reader=reader,
        )
        result["refresh_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
        result["reader_only_refresh_reads"] = _delta(
            before_refresh, _read_metrics(reader),
        )
        result["refresh_cache_hit"] = last_league_catalog_metrics().get("cache_hit")
        result["refresh_same_size"] = (
            len(refresh["competitions"]) == len(catalog["competitions"])
        )
        result["refresh_same_entries"] = (
            refresh["competitions"] == catalog["competitions"]
        )
        result["catalog_source"] = catalog["source"]
        result["catalog_native"] = catalog["native"]
        result["catalog_competitions"] = len(catalog["competitions"])
        result["catalog_sample"] = catalog["competitions"][:max(0, limit)]
        if full_catalog:
            result["catalog_entries"] = _safe_catalog_entries(catalog["competitions"])
        result["distribution"] = _distribution(catalog["competitions"])
        result["ok"] = catalog["source"] == LEAGUE_CATALOG_SOURCE_NATIVE
        if not result["ok"]:
            result["error"] = "native competition catalog unavailable"
        result.update(_UNSUPPORTED_PROVIDER_REPORT)
    result["metrics"] = last_league_catalog_metrics()
    return result


def probe_without_game(
    output: dict[str, Any], *, limit: int, full_catalog: bool = False,
) -> dict[str, Any]:
    """Degraded path: no game read, only what ``output`` already describes."""
    started = time.perf_counter()
    catalog = unavailable_league_catalog(output, scope_id="probe-no-game")
    competitions = list(catalog["competitions"])
    report = {
        "mode": "no-game",
        "ok": True,
        "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 1),
        "catalog_source": catalog["source"],
        "catalog_native": catalog["native"],
        "catalog_competitions": len(competitions),
        "catalog_sample": competitions[:max(0, limit)],
        "distribution": _distribution(competitions),
    }
    report.update(_UNSUPPORTED_PROVIDER_REPORT)
    if full_catalog:
        report["catalog_entries"] = _safe_catalog_entries(competitions)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe the read-only native competition catalog.",
    )
    parser.add_argument(
        "--state-file", type=Path, default=None,
        help="saved GET /api/state JSON body (or its 'output' object)",
    )
    parser.add_argument(
        "--no-game", action="store_true",
        help="skip the live game read and probe the degraded payload only",
    )
    parser.add_argument(
        "--limit", type=int, default=5,
        help="how many catalog entries to print as a sample",
    )
    parser.add_argument(
        "--report-path", type=Path, default=None,
        help="write the UTF-8 JSON report directly to this file",
    )
    parser.add_argument(
        "--label", default="",
        help="optional capture label, such as before or after",
    )
    parser.add_argument(
        "--full-catalog", action="store_true",
        help="include all catalog ids, names, short names, and reputations",
    )
    args = parser.parse_args()

    output = _load_state_output(args.state_file)
    if args.no_game:
        report = probe_without_game(
            output, limit=args.limit, full_catalog=args.full_catalog,
        )
    else:
        try:
            report = probe_live(
                output, limit=args.limit, full_catalog=args.full_catalog,
            )
        except Exception as error:  # noqa: BLE001 - a probe reports, it never raises
            report = {
                "mode": "live",
                "ok": False,
                "catalog_source": "unavailable",
                "error": f"{error.__class__.__name__}: {error}",
                **_UNSUPPORTED_PROVIDER_REPORT,
            }
    if args.label:
        report["label"] = args.label
    report_json = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.report_path is not None:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(report_json + "\n", encoding="utf-8")
        print(json.dumps({
            "ok": report.get("ok"),
            "label": report.get("label"),
            "catalog_source": report.get("catalog_source"),
            "catalog_competitions": report.get("catalog_competitions"),
            "report_path": str(args.report_path.resolve()),
            "error": report.get("error"),
        }, ensure_ascii=False, indent=2))
    else:
        print(report_json)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
