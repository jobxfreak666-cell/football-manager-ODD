"""Full native competition catalog with an explicit standings-availability contract.

FMODD renders league tables from two different sources:

* the native (in-game) league stage table, formatted by
  ``tools.league_standings._native_format_standings``, and
* a reconstructed table built from the results FMODD itself observed,
  ``tools.league_standings.build_standings``.

``public_league_standings`` merges the two and only reports competitions that
have at least one of them.  The web UI additionally needs to search *every*
competition the save knows about - including the ones that have no table yet -
so this module exposes the whole native competition table and states, per
competition, whether a table is available and why native formatting was not
used.

The payload published as ``app.state.league_catalog``::

    {
      "source": "native_competition_table" | "unavailable",
      "scope_id": str,
      "game_layout": "fm24" | "fm26" | "",
      "native": bool,
      "scanned_at": str,                 # ISO-8601 UTC of the native scan
      "competitions": [
        {
          "competition_id": int,
          "name": str,
          "short_name": str,
          "reputation": int,             # 0 when the layout has no verified
                                         # competition reputation offset.
                                         # 0 is a real value, not a gap.
          "standings_available": bool,   # native OR reconstructed table
          "standings_source": "native" | "reconstructed" | None,
          "standings_reason": str | None # why it is not native; None if it is
        },
        ...
      ],
    }

``standings_reason`` codes
==========================

Every code below maps 1:1 onto a real branch of
``tools/league_standings._native_format_standings``.  The mapping is exposed as
the single public constant :data:`STANDINGS_REASON_CODES` (code ->
``(condition, line_range)``); its insertion order is the precedence order, so
when several conditions apply the first one in that order is reported.

``no_native_format``
    ``src/tools/league_standings.py:468`` - the competition id never appears in
    ``output["competition_formats"]``, so the formatting loop never visits it.
    This is also the code for "this save has no league-stage/table data for
    that competition yet".  A zero ``competition_id`` (the ``:473`` guard) is
    folded in here: an id-less format row cannot name a published competition.
    A competition in this state is reported with ``standings_source = None``
    and ``standings_available = False``; the UI must render an explicit
    "no standings yet" entry rather than a fabricated 0-0 table.
``not_a_league``
    ``:474`` - ``str(item["competition_kind"]) != "league"``.
``not_league_opening_stage``
    ``:475`` - ``str(item["opening_stage_type"]) != "league"``.
``opening_field_incomplete``
    ``:476`` - ``not item["opening_field_complete"]``.
``opening_slot_count_invalid``
    ``:477`` - ``expected < 2 or len(opening_teams) != expected``, where
    ``expected = int(item["opening_slot_count"] or 0)``.
``team_standing_unverified``
    ``:478`` - ``any(not team["native_standing_verified"])``: at least one
    opening team has no verified native standing row.
``native_rows_incomplete``
    ``:483-486`` with the ``:511-512`` guard - an opening team has no id
    (``int(team["id"] or 0) == 0``), so ``rows`` is reset to ``[]`` and
    ``len(rows) != expected`` rejects the competition.
``reconstructed_ahead_of_native``
    ``:521-535`` - the reconstructed rows cover exactly the same teams and every
    reconstructed ``played`` count is >= the native one while at least one is
    strictly greater, so the native table is deliberately suppressed in favour
    of the reconstructed one (it is more up to date).

    A competition whose id is in neither the native nor the reconstructed list
    gets the branch its ``competition_formats`` row fails (``not_a_league`` for a
    cup, say), or ``no_native_format`` when the row is eligible and merely has no
    published rows yet.  A competition that *is* reconstructed but not native
keeps ``standings_available = True`` with ``standings_reason`` explaining why
native formatting did not apply - availability and native-ness are separate
questions on purpose.

There is no league-vs-cup type field in the native competition table, and the
native stage markers only cover a small, partly ``unknown`` subset, so this
module never infers a competition "kind".  The only kind signal it uses is
``output["competition_formats"]`` membership, exactly like the standings code.

Reading is strictly read-only: :func:`build_league_catalog` borrows the normal
game read lease, lists the native ``competition`` pointer table and reads each
competition object plus its reputation byte.  It never opens a writable process,
installs a hook, or touches a save/account.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from contextlib import ExitStack
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from tools.database_index import DatabaseIndex, database_index_for_reader


LEAGUE_CATALOG_SOURCE_NATIVE = "native_competition_table"
LEAGUE_CATALOG_SOURCE_UNAVAILABLE = "unavailable"

#: Which table produced a competition's standings rows.
STANDINGS_SOURCE_NATIVE = "native"
STANDINGS_SOURCE_RECONSTRUCTED = "reconstructed"

#: code -> (condition, ``src/tools/league_standings.py`` line range).
#:
#: Insertion order IS the reporting precedence: when several conditions hold for
#: the same ``competition_formats`` row, the first code in this order is the one
#: published in ``standings_reason``.
STANDINGS_REASON_CODES: dict[str, tuple[str, str]] = {
    "no_native_format": (
        "The competition id is never visited by the loop over "
        "output['competition_formats'] (:468); a zero competition id (:473) is "
        "folded in here because an id-less format row cannot name a published "
        "competition.",
        ":468, :473",
    ),
    "not_a_league": (
        "str(item['competition_kind']) != 'league'.",
        ":474",
    ),
    "not_league_opening_stage": (
        "str(item['opening_stage_type']) != 'league'.",
        ":475",
    ),
    "opening_field_incomplete": (
        "not item['opening_field_complete'].",
        ":476",
    ),
    "opening_slot_count_invalid": (
        "expected < 2 or len(opening_teams) != expected where "
        "expected = int(item['opening_slot_count'] or 0).",
        ":477",
    ),
    "team_standing_unverified": (
        "any(not team['native_standing_verified'] for team in opening_teams): "
        "at least one opening team has no verified native standing row.",
        ":478",
    ),
    "native_rows_incomplete": (
        "An opening team has no id (int(team['id'] or 0) == 0): rows is reset "
        "to [] and the len(rows) != expected guard rejects the competition.",
        ":483-486, :511-512",
    ),
    "reconstructed_ahead_of_native": (
        "The reconstructed rows cover exactly the native teams, every "
        "reconstructed played count is >= the native one and at least one is "
        "strictly greater, so the native table is suppressed as out of date.",
        ":521-535",
    ),
}

#: Reporting precedence, derived from :data:`STANDINGS_REASON_CODES` order.
STANDINGS_REASON_ORDER: tuple[str, ...] = tuple(STANDINGS_REASON_CODES)

_CATALOG_LAYOUTS = frozenset({"fm24", "fm26"})
_REPUTATION_MAX = 200
# One page around the competition object covers the vtable, the uid and the
# reputation byte (fm26 offset 0x188), so a single read serves the whole row.
_PREFETCH_BYTES = 0x200
_NATIVE_CACHE_MAX = 4
_NATIVE_CACHE_MAX_AGE_SECONDS = 5.0

_LOCK = threading.RLock()
# (scope_id, layout, session_generation, index identity) -> cached native scan.
# The pointer token catches table membership changes; the age bound also refreshes
# names and reputation that can change without changing that pointer table.
_NATIVE_CACHE: "OrderedDict[tuple[Any, ...], dict[str, Any]]" = OrderedDict()
_GENERATION = 0
_SCAN_COUNT = 0
_LAST_METRICS: dict[str, Any] = {}


def catalog_layout(output: Mapping[str, Any] | None) -> str:
    """Return the published ``game_layout`` value for ``output``."""
    value = str((output or {}).get("game_layout") or "") if output else ""
    return value if value in _CATALOG_LAYOUTS else ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _short_text(value: Any) -> str:
    return str(value or "").strip()


def _reputation_of(reader: Any, address: int) -> int:
    """Read the competition reputation byte, mirroring preview_cup_odds.

    Returns 0 when the active layout has no verified competition reputation
    offset, or when the value is outside the accepted range.  0 is also a real
    native value (many competitions are genuinely unrated), so it must not be
    dropped or treated as "missing" further down.
    """
    layout = getattr(reader, "layout", None)
    offset = getattr(layout, "competition_reputation_offset", None)
    width = getattr(layout, "competition_reputation_bytes", None)
    if offset is None or width not in (1, 2):
        return 0
    try:
        if int(width) == 2:
            value = reader.u16(int(address) + int(offset))
        else:
            value = reader.u8(int(address) + int(offset))
    except (OSError, RuntimeError, TypeError, ValueError):
        return 0
    if value is None:
        return 0
    value = int(value)
    return value if 0 <= value <= _REPUTATION_MAX else 0


def _object_address(row: Mapping[str, Any]) -> int:
    raw = row.get("address")
    if isinstance(raw, int):
        return raw
    text = _short_text(raw)
    if not text:
        return 0
    try:
        return int(text, 16)
    except ValueError:
        return 0


def _index_for(reader: Any) -> Any:
    """Return the native index to scan with, or ``None`` when it is unavailable.

    A borrowed game reader carries ``database_index_provider``, which hands back
    the read session's long-lived index (already warmed in a background thread).
    When that provider exists but yields nothing the session itself could not
    build an index, so building a second one here would pay a full cold scan -
    ~1.3 s against a live 8095-competition save - on a refresh path that holds
    the state lock.  Returning ``None`` lets the caller degrade instead.

    A reader without the provider at all (probes, tests, offline readers) still
    gets a request-local index, which is what those callers want.
    """
    provider = getattr(reader, "database_index_provider", None)
    if callable(provider):
        index = database_index_for_reader(reader)
        if index is not None:
            return index
        return None
    return DatabaseIndex(reader)


def scan_native_competitions(reader: Any) -> tuple[dict[str, Any], ...]:
    """Read every row of the native ``competition`` pointer table.

    Returns one ``{"competition_id", "name", "short_name", "reputation"}`` dict
    per distinct competition id, sorted by id.  Costs one pointer-table refresh
    plus a page read and two string reads per object.

    Raises ``RuntimeError`` when the native index is unavailable or an object
    read fails, so a caller never mistakes an incomplete scan for a full catalog.
    """
    index = _index_for(reader)
    if index is None:
        raise RuntimeError("native competition index unavailable")
    addresses = index.addresses("competition", force=True)
    rows: dict[int, dict[str, Any]] = {}
    for address in addresses:
        address = int(address)
        if not address:
            continue
        try:
            reader.prefetch(address, _PREFETCH_BYTES)
        except (OSError, RuntimeError, TypeError, ValueError):
            pass
        try:
            native = reader.competition(address)
        except (OSError, RuntimeError, TypeError, ValueError):
            raise RuntimeError("native competition object read failed") from None
        if native is None:
            raise RuntimeError("native competition object read failed")
        if not native:
            continue
        competition_id = _as_int(native.get("id"))
        if competition_id <= 0:
            continue
        name = _short_text(native.get("name"))
        short_name = _short_text(native.get("short_name"))
        reputation = _reputation_of(reader, _object_address(native))
        previous = rows.get(competition_id)
        if previous is None:
            rows[competition_id] = {
                "competition_id": competition_id,
                "name": name or str(competition_id),
                "short_name": short_name or name or str(competition_id),
                "reputation": reputation,
            }
            continue
        # The pointer table may hold the same competition at several addresses;
        # keep the richest row instead of publishing duplicates.
        if name and (not previous["name"] or previous["name"] == str(competition_id)):
            previous["name"] = name
        if short_name and (
            not previous["short_name"]
            or previous["short_name"] == str(competition_id)
            or previous["short_name"] == previous["name"]
        ):
            previous["short_name"] = short_name
        if reputation > int(previous["reputation"]):
            previous["reputation"] = reputation
    return tuple(rows[key] for key in sorted(rows))


def _cached_native_rows(
    reader: Any, scope_id: str, layout: str, *, force: bool,
) -> tuple[tuple[dict[str, Any], ...], str, bool]:
    """Return ``(rows, scanned_at, cache_hit)`` for the native competition scan."""
    global _SCAN_COUNT
    index = _index_for(reader)
    if index is None:
        raise RuntimeError("native competition index unavailable")
    session_generation = int(getattr(reader, "session_generation", 0) or 0)
    key = (str(scope_id or ""), layout, session_generation, id(index))
    # Refreshing the pointer table is a ~65 KiB read; the expensive part is the
    # per-object walk. The token catches membership changes while a short age
    # bound catches in-place name and reputation changes.
    token = tuple(index.table_token("competition"))
    now = time.monotonic()
    with _LOCK:
        entry = _NATIVE_CACHE.get(key)
        if (
            not force
            and entry is not None
            and entry["generation"] == _GENERATION
            and entry["token"] == token
            and now - entry["cached_at_monotonic"] < _NATIVE_CACHE_MAX_AGE_SECONDS
        ):
            _NATIVE_CACHE.move_to_end(key)
            return entry["rows"], entry["scanned_at"], True
    started = time.perf_counter()
    rows = scan_native_competitions(reader)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    scanned_at = _now_iso()
    # Re-read the token AFTER the walk: the scan forces a table refresh, so this
    # is the fingerprint of the very rows just captured.  Storing ``token`` here
    # would cache a pre-scan fingerprint and could serve stale rows once when
    # the table changed between the check and the walk.
    token = tuple(index.table_token("competition"))
    with _LOCK:
        _SCAN_COUNT += 1
        _NATIVE_CACHE[key] = {
            "token": token,
            "generation": _GENERATION,
            "rows": rows,
            "scanned_at": scanned_at,
            "cached_at_monotonic": time.monotonic(),
            "scan_ms": elapsed_ms,
        }
        _NATIVE_CACHE.move_to_end(key)
        while len(_NATIVE_CACHE) > _NATIVE_CACHE_MAX:
            _NATIVE_CACHE.popitem(last=False)
    return rows, scanned_at, False


def invalidate_league_catalog() -> None:
    """Drop cached native scans (next build re-reads the competition table)."""
    global _GENERATION
    with _LOCK:
        _GENERATION += 1
        _NATIVE_CACHE.clear()


def last_league_catalog_metrics() -> dict[str, Any]:
    """Return counters describing the most recent catalog build."""
    with _LOCK:
        metrics = dict(_LAST_METRICS)
        metrics["scan_count"] = _SCAN_COUNT
        metrics["generation"] = _GENERATION
        metrics["cached_scopes"] = len(_NATIVE_CACHE)
    return metrics


def formats_index(output: Mapping[str, Any] | None) -> dict[int, dict[str, Any]]:
    """Map competition id -> its ``output["competition_formats"]`` row."""
    index: dict[int, dict[str, Any]] = {}
    for item in (output or {}).get("competition_formats") or []:
        if not isinstance(item, Mapping):
            continue
        competition_id = _as_int(item.get("competition_id"))
        if competition_id <= 0:
            continue
        index.setdefault(competition_id, dict(item))
    return index


def native_skip_reason(
    item: Mapping[str, Any] | None,
    reconstructed_teams: Sequence[Mapping[str, Any]] | None = None,
) -> str | None:
    """Return why ``item`` does not produce a native table, or ``None``.

    Walks the branches of ``league_standings._native_format_standings`` in the
    same order it does, and returns the first code of
    :data:`STANDINGS_REASON_CODES` that applies.  ``None`` means the row is
    eligible for native formatting.
    """
    if item is None:
        # :468 - the id is never visited by the competition_formats loop.
        return "no_native_format"
    teams = [team for team in (item.get("opening_teams") or []) if isinstance(team, Mapping)]
    expected = _as_int(item.get("opening_slot_count"))
    if _as_int(item.get("competition_id")) <= 0:
        # :473 - an id-less row cannot name a published competition.
        return "no_native_format"
    if str(item.get("competition_kind") or "") != "league":  # :474
        return "not_a_league"
    if str(item.get("opening_stage_type") or "") != "league":  # :475
        return "not_league_opening_stage"
    if not item.get("opening_field_complete"):  # :476
        return "opening_field_incomplete"
    if expected < 2 or len(teams) != expected:  # :477
        return "opening_slot_count_invalid"
    if any(not team.get("native_standing_verified") for team in teams):  # :478
        return "team_standing_unverified"
    for team in teams:
        if _as_int(team.get("id")) <= 0:  # :483-486 -> :511-512
            return "native_rows_incomplete"
    if len(teams) != expected:  # :511-512, unreachable after the :477 guard
        return "native_rows_incomplete"
    native_teams = {_as_int(team.get("id")): team for team in teams}
    reconstructed = {
        _as_int(team.get("team_id")): team
        for team in (reconstructed_teams or [])
        if isinstance(team, Mapping)
    }
    reconstructed.pop(0, None)
    if (
        len(reconstructed) == expected  # :522
        and reconstructed.keys() == native_teams.keys()  # :523
        and all(  # :524-528
            _as_int(reconstructed[team_id].get("played")) >= _as_int(team.get("played"))
            for team_id, team in native_teams.items()
        )
        and any(  # :529-533
            _as_int(reconstructed[team_id].get("played")) > _as_int(team.get("played"))
            for team_id, team in native_teams.items()
        )
    ):
        return "reconstructed_ahead_of_native"
    return None


def _explained_reason(
    item: Mapping[str, Any] | None,
    reconstructed_teams: Sequence[Mapping[str, Any]] | None,
) -> str:
    """Explain, for a competition with a reconstructed table, why it is not native.

    The mirror reproduces every skip branch, so it only returns ``None`` here if
    upstream gains a branch this module does not model.  In that drift case the
    last modelled suppression is reported rather than a ``null`` reason, because
    the frozen contract reserves a null reason for "native table present".
    """
    reason = native_skip_reason(item, reconstructed_teams)
    return reason or "reconstructed_ahead_of_native"


def _standings_entries(
    standings: Mapping[str, Any] | None,
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    """Split published standings into (native by id, reconstructed by id)."""
    native: dict[int, dict[str, Any]] = {}
    reconstructed: dict[int, dict[str, Any]] = {}
    for competition in (standings or {}).get("competitions") or []:
        if not isinstance(competition, Mapping):
            continue
        competition_id = _as_int(competition.get("competition_id"))
        if competition_id <= 0:
            continue
        if competition.get("source") == "native_league_stage":
            native[competition_id] = dict(competition)
        else:
            reconstructed[competition_id] = dict(competition)
    return native, reconstructed


def catalog_competitions(
    native_rows: Sequence[Mapping[str, Any]],
    standings: Mapping[str, Any] | None,
    output: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Join the native table, the published standings and the format rows."""
    native_standings, reconstructed_standings = _standings_entries(standings)
    formats = formats_index(output)
    entries: dict[int, dict[str, Any]] = {}
    for row in native_rows:
        competition_id = _as_int(row.get("competition_id"))
        if competition_id <= 0:
            continue
        name = _short_text(row.get("name")) or str(competition_id)
        short_name = (
            _short_text(row.get("short_name"))
            or _short_text(row.get("name"))
            or str(competition_id)
        )
        reputation = _as_int(row.get("reputation"))
        previous = entries.get(competition_id)
        if previous is None:
            entries[competition_id] = {
                "competition_id": competition_id,
                "name": name,
                "short_name": short_name,
                "reputation": reputation,
            }
            continue
        # Same policy as scan_native_competitions: keep the richest row rather
        # than letting a later, thinner duplicate overwrite a real name.
        placeholder = str(competition_id)
        if name != placeholder and previous["name"] == placeholder:
            previous["name"] = name
        if (
            short_name != placeholder
            and short_name != previous["name"]
            and previous["short_name"] in (placeholder, previous["name"])
        ):
            previous["short_name"] = short_name
        if reputation > int(previous["reputation"]):
            previous["reputation"] = reputation
    for source_by_id in (reconstructed_standings, native_standings):
        for competition_id, competition in source_by_id.items():
            name = _short_text(competition.get("competition_name")) or str(competition_id)
            entry = entries.get(competition_id)
            reputation = _as_int(competition.get("reputation"))
            if entry is None:
                entries[competition_id] = {
                    "competition_id": competition_id,
                    "name": name,
                    "short_name": name,
                    "reputation": reputation,
                }
                continue
            if not entry["name"] or entry["name"] == str(competition_id):
                entry["name"] = name
            if reputation:
                entry["reputation"] = reputation
    for competition_id, item in formats.items():
        if competition_id in entries:
            continue
        name = _short_text(item.get("competition_name")) or str(competition_id)
        entries[competition_id] = {
            "competition_id": competition_id,
            "name": name,
            "short_name": name,
            "reputation": 0,
        }
    competitions: list[dict[str, Any]] = []
    for competition_id, entry in entries.items():
        format_item = formats.get(competition_id)
        native_entry = native_standings.get(competition_id)
        reconstructed_entry = reconstructed_standings.get(competition_id)
        if native_entry is not None:
            available = True
            standings_source: str | None = STANDINGS_SOURCE_NATIVE
            reason: str | None = None
        elif reconstructed_entry is not None:
            available = True
            standings_source = STANDINGS_SOURCE_RECONSTRUCTED
            reason = _explained_reason(
                format_item, reconstructed_entry.get("teams") or [],
            )
        else:
            available = False
            standings_source = None
            # The competition is in neither published list, so there is no table
            # to render.  Prefer the mirror's real branch (``not_a_league`` for a
            # cup, ``opening_field_incomplete`` for an early-season league); when
            # the mirror finds no skip branch it was merely eligible and simply
            # has no rows published yet, which the contract names
            # ``no_native_format`` and the UI renders as "no standings yet".
            reason = native_skip_reason(format_item, ()) or "no_native_format"
        competitions.append({
            "competition_id": competition_id,
            "name": entry["name"],
            "short_name": entry["short_name"],
            "reputation": int(entry["reputation"]),
            "standings_available": available,
            "standings_source": standings_source,
            "standings_reason": reason,
        })
    competitions.sort(key=lambda item: (
        -int(item["reputation"]),
        str(item["name"]).casefold(),
        int(item["competition_id"]),
    ))
    return competitions


def _unavailable_payload(
    scope_id: str, layout: str, output: Mapping[str, Any] | None,
    standings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Degraded payload: every competition derivable from ``output``, honestly.

    The published shape is identical to the native one - never a null or a
    missing key - so the frontend has exactly one payload contract to handle.
    """
    competitions = catalog_competitions((), standings, output)
    return {
        "source": LEAGUE_CATALOG_SOURCE_UNAVAILABLE,
        "scope_id": str(scope_id or ""),
        "game_layout": layout,
        "native": False,
        "scanned_at": _now_iso(),
        "competitions": competitions,
    }


def unavailable_league_catalog(
    output: Mapping[str, Any] | None = None, *, scope_id: str = "",
) -> dict[str, Any]:
    """Return the documented degraded payload without touching the game at all.

    Used when there is no verified save to read: borrowing a read session would
    open the process just to confirm there is nothing to read.  The shape is the
    same six keys as a native build, so the frontend has one contract.
    """
    return _unavailable_payload(
        str(scope_id or ""), catalog_layout(output), output,
        _published_standings(output),
    )


def build_league_catalog(
    output: Mapping[str, Any] | None = None,
    *,
    scope_id: str = "",
    standings: Mapping[str, Any] | None = None,
    reader: Any | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Build the ``league_catalog`` payload for ``output``.

    ``standings`` is the already-published ``public_league_standings(output)``
    payload; passing it keeps the catalog consistent with the tables the state
    endpoint renders in the same request (and avoids recomputing them).
    ``reader`` is only used by probes/tests; the normal path borrows the game
    read lease.  Never raises: a failed native read degrades to
    ``source = "unavailable"`` with the entries ``output`` can still describe.
    """
    started = time.perf_counter()
    payload_output: Mapping[str, Any] = output if isinstance(output, Mapping) else {}
    scope = str(scope_id or "")
    layout = catalog_layout(payload_output)
    if standings is None:
        standings = _published_standings(payload_output)
    native_rows: tuple[dict[str, Any], ...] = ()
    scanned_at = ""
    cache_hit = False
    source = LEAGUE_CATALOG_SOURCE_UNAVAILABLE
    note = "native competition table unavailable"
    with ExitStack() as stack:
        active_reader = reader
        if active_reader is None:
            try:
                from tools.game_session import borrow_game_reader

                active_reader = stack.enter_context(borrow_game_reader())
            except Exception as error:  # noqa: BLE001 - never break a refresh
                note = f"no live game read session: {error.__class__.__name__}"
                active_reader = None
        if active_reader is not None:
            try:
                native_rows, scanned_at, cache_hit = _cached_native_rows(
                    active_reader, scope, layout, force=force,
                )
            except Exception as error:  # noqa: BLE001 - degrade, never raise
                note = (
                    f"native competition table read failed: "
                    f"{error.__class__.__name__}: {error}"
                )
                native_rows = ()
            else:
                source = LEAGUE_CATALOG_SOURCE_NATIVE
                note = ""
    if source == LEAGUE_CATALOG_SOURCE_NATIVE:
        competitions = catalog_competitions(native_rows, standings, payload_output)
        payload = {
            "source": source,
            "scope_id": scope,
            "game_layout": layout,
            "native": True,
            "scanned_at": scanned_at or _now_iso(),
            "competitions": competitions,
        }
    else:
        payload = _unavailable_payload(scope, layout, payload_output, standings)
    with _LOCK:
        _LAST_METRICS.clear()
        _LAST_METRICS.update({
            "source": payload["source"],
            "native": payload["native"],
            "competitions": len(payload["competitions"]),
            "standings_available": sum(
                1 for item in payload["competitions"] if item["standings_available"]
            ),
            "cache_hit": cache_hit,
            "scan_count": _SCAN_COUNT,
            "elapsed_ms": (time.perf_counter() - started) * 1000.0,
            "note": note,
            "scope_id": scope,
            "game_layout": layout,
        })
    return payload


def _published_standings(output: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """Best-effort standings payload for callers that did not pass one."""
    if not output:
        return None
    try:
        from tools.league_standings import public_league_standings

        return public_league_standings(dict(output))
    except Exception:  # noqa: BLE001 - degrade to the native table only
        return None


__all__ = [
    "LEAGUE_CATALOG_SOURCE_NATIVE",
    "LEAGUE_CATALOG_SOURCE_UNAVAILABLE",
    "STANDINGS_REASON_CODES",
    "STANDINGS_REASON_ORDER",
    "STANDINGS_SOURCE_NATIVE",
    "STANDINGS_SOURCE_RECONSTRUCTED",
    "build_league_catalog",
    "catalog_competitions",
    "catalog_layout",
    "formats_index",
    "invalidate_league_catalog",
    "last_league_catalog_metrics",
    "native_skip_reason",
    "scan_native_competitions",
    "unavailable_league_catalog",
]
