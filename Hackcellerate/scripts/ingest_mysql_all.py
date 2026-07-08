"""Bulk-ingest every text-bearing table from a MySQL database.

Introspects information_schema, auto-picks id/title/text/extra columns per table,
skips obvious junk (audit logs, sessions, mappings, history, sequelizemeta, etc.),
and POSTs one /ingest/source request per table.

Usage:
  python scripts/ingest_mysql_all.py --url "mysql+pymysql://root:root@localhost:3306/phccp_uber_dev_uatv2_0621"
  python scripts/ingest_mysql_all.py --url "..." --dry-run
  python scripts/ingest_mysql_all.py --url "..." --max-per-table 500
  python scripts/ingest_mysql_all.py --url "..." --only notes,mailcontents
  python scripts/ingest_mysql_all.py --url "..." --min-rows 10 --max-rows 50000
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from typing import Any
from urllib.parse import urlparse

import requests
from sqlalchemy import create_engine, text

API_URL = "http://localhost:8000/ingest/source"

# Table name patterns to always skip (regex, case-insensitive)
SKIP_PATTERNS = [
    r".*audit.*log.*",
    r".*_archive$",
    r".*statehistor.*",
    r".*_history$",
    r".*mapping[s]?$",
    r".*mapper[s]?$",
    r".*session[s]?$",
    r"sequelizemeta",
    r"^settings$",
    r"^licenses$",
    r".*permission[s]?$",
    r".*role[s]?$",
    r".*rolemapping.*",
    r".*queue$",
    r".*failurelog.*",
    r"^slices$",
    r"^images$",
    r"^series$",
    r"^files$",
    r"^cities$",
    r"^countries$",
    r"^states$",
    r"^languages$",
    r"^educations$",
    r"^employments$",
    r"^modalities$",
    r"^cohorts$",
    r".*ad(models|roles)$",
    r"^vmauditlogs$",
    r"^usersessions$",
    r"^uservmassignments$",
    r"^dicomconformanceconfig$",
    r"^ohif_metadata$",
    r"^ohif_config$",
    r"^ohif_annotations$",
    r"^viewerconfig$",
    r"^systemobjects.*",
    r"^workflowstate.*",
    r"^workflowguardmapping$",
    r"^workflowoutputactions$",
    r"^workflowpipelinesmappings$",
    r"^workflowtypes$",
    r"^formgroup.*",
    r".*groupmembers$",
    r".*grouptypesmaster$",
    r".*taskstatusmaster$",
    r".*projectstatemasters$",
    r".*projectpackagemasters$",
    r".*teammembers$",
    r".*teamdefinitions$",
    r".*taskteams.*",
    r".*taskcollaboratorstatus$",
]

SKIP_RE = re.compile("|".join(f"(?:{p})" for p in SKIP_PATTERNS), re.IGNORECASE)

# Column names to prefer as title, in order
TITLE_HINTS = ["title", "name", "subject", "label", "code", "display_name", "displayname"]

# Column names to exclude entirely (secrets / sensitive)
SECRET_HINTS = ["password", "passwd", "pwd", "secret", "token", "apikey", "api_key",
                "salt", "signature", "auth", "credential", "privatekey", "private_key"]

# Data types that shouldn't be embedded or stored as metadata
BINARY_TYPES = {"blob", "mediumblob", "longblob", "tinyblob", "binary", "varbinary", "geometry"}


def is_wide_text(data_type: str, char_len: int | None) -> bool:
    dt = data_type.lower()
    if dt in ("text", "mediumtext", "longtext", "tinytext"):
        return True
    if dt == "varchar" and (char_len or 0) >= 100:
        return True
    return False


def is_short_scalar(data_type: str, char_len: int | None) -> bool:
    """Short varchars, numbers, dates, bools — safe to embed AND to store as metadata."""
    dt = data_type.lower()
    if dt in ("varchar", "char") and 1 <= (char_len or 0) < 100:
        return True
    if dt in ("int", "bigint", "smallint", "mediumint", "tinyint", "integer",
              "decimal", "numeric", "float", "double", "real",
              "date", "datetime", "timestamp", "time", "year", "bit", "bool", "boolean"):
        return True
    if dt == "enum":
        return True
    return False


def is_secret(col_name: str) -> bool:
    lower = col_name.lower()
    return any(bad in lower for bad in SECRET_HINTS)


def is_binary(data_type: str) -> bool:
    return data_type.lower() in BINARY_TYPES


def pick_title_column(cols: list[dict]) -> str | None:
    lookup = {c["name"].lower(): c["name"] for c in cols}
    for hint in TITLE_HINTS:
        if hint in lookup:
            return lookup[hint]
    for c in cols:
        if is_short_scalar(c["type"], c["char_len"]) and c["type"].lower() in ("varchar", "char"):
            return c["name"]
    return None


def introspect(engine, db_name: str) -> dict[str, dict[str, Any]]:
    """Return {table_name: {pk, cols, wide_text_cols, short_scalar_cols, row_count}}."""
    with engine.connect() as c:
        cols_rows = c.execute(text("""
            SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, COLUMN_KEY, ORDINAL_POSITION
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = :db
            ORDER BY TABLE_NAME, ORDINAL_POSITION
        """), {"db": db_name}).fetchall()

        table_rows = c.execute(text("""
            SELECT TABLE_NAME, IFNULL(TABLE_ROWS, 0)
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = :db AND TABLE_TYPE = 'BASE TABLE'
        """), {"db": db_name}).fetchall()

    row_counts = {t: n for t, n in table_rows}
    tables: dict[str, dict[str, Any]] = {}
    for tname, cname, dtype, clen, key, _ordpos in cols_rows:
        if tname not in row_counts:
            continue
        t = tables.setdefault(tname, {
            "pk": None, "cols": [], "wide_text_cols": [], "short_scalar_cols": [],
        })
        col = {"name": cname, "type": dtype, "char_len": clen, "key": key}
        t["cols"].append(col)
        if key == "PRI" and t["pk"] is None:
            t["pk"] = cname
        if is_secret(cname) or is_binary(dtype):
            continue
        if is_wide_text(dtype, clen):
            t["wide_text_cols"].append(cname)
        elif is_short_scalar(dtype, clen):
            t["short_scalar_cols"].append(cname)

    for tname, info in tables.items():
        info["row_count"] = row_counts.get(tname, 0)
    return tables


def build_plan(tables: dict, only: set[str] | None, min_rows: int, max_rows: int,
               embed_all_fields: bool) -> list[dict]:
    plan = []
    for tname, info in sorted(tables.items()):
        if only is not None and tname.lower() not in only:
            continue
        if only is None and SKIP_RE.match(tname):
            continue
        if info["pk"] is None:
            continue
        row_count = info["row_count"] or 0
        if row_count < min_rows or row_count > max_rows:
            continue

        wide = info["wide_text_cols"]
        shorts = info["short_scalar_cols"]

        # Need SOMETHING to embed. If no wide text AND embed_all_fields=False, skip.
        if not wide and not embed_all_fields:
            continue

        title = pick_title_column(info["cols"]) or info["pk"]

        # text_columns: what gets embedded/vector-searchable
        # - Prepend short scalars (pk, title, statuses, dates, ids, names, etc.)
        #   so "id 12345" or "status=active" is discoverable via vector search.
        # - Follow with wide text columns (the main prose).
        embed_cols: list[str] = []
        seen: set[str] = set()

        def add(c: str) -> None:
            if c and c not in seen:
                embed_cols.append(c)
                seen.add(c)

        add(info["pk"])
        add(title)
        for c in shorts:
            add(c)
        for c in wide[:6]:  # cap wide cols to avoid embedding entire dumps
            add(c)

        # extra_columns: everything scalar-safe becomes metadata (filterable)
        # Includes pk/title/shorts/wide-short. Skip only huge TEXT blobs (already embedded).
        extras: list[str] = []
        for c in info["cols"]:
            n = c["name"]
            if is_secret(n) or is_binary(c["type"]):
                continue
            if is_wide_text(c["type"], c["char_len"]):
                continue  # too big for metadata; already in text
            extras.append(n)

        # SELECT list = union
        select_cols: list[str] = []
        seen2: set[str] = set()
        for c in embed_cols + extras:
            if c not in seen2:
                select_cols.append(c)
                seen2.add(c)

        plan.append({
            "table": tname,
            "row_count": row_count,
            "id_column": info["pk"],
            "title_column": title,
            "text_columns": embed_cols,
            "extra_columns": extras,
            "select_cols": select_cols,
            "wide_count": len(wide),
            "short_count": len(shorts),
        })
    return plan


def build_query(entry: dict, limit: int) -> str:
    quoted = ", ".join(f"`{c}`" for c in entry["select_cols"])
    # No WHERE filter: we want every row, including ones without wide text
    # (metadata-only rows are still useful for ID / field lookups).
    return (
        f"SELECT {quoted} FROM `{entry['table']}` "
        f"ORDER BY `{entry['id_column']}` DESC "
        f"LIMIT {limit}"
    )


def ingest_table(entry: dict, url: str, limit: int, db_label: str, api_url: str) -> dict:
    payload = {
        "type": "sql",
        "max_records": limit,
        "tags": [db_label, entry["table"]],
        "config": {
            "connection_url": url,
            "query": build_query(entry, limit),
            "id_column": entry["id_column"],
            "title_column": entry["title_column"],
            "text_columns": entry["text_columns"],
            "extra_columns": entry["extra_columns"],
            "source_label": f"{db_label}_{entry['table']}",
            "doc_type": entry["table"],
            "fetch_size": min(limit, 500),
        },
    }
    r = requests.post(api_url, json=payload, timeout=600)
    r.raise_for_status()
    return r.json()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True, help="SQLAlchemy URL, e.g. mysql+pymysql://root:root@localhost:3306/dbname")
    p.add_argument("--api-url", default=API_URL)
    p.add_argument("--dry-run", action="store_true", help="Print the plan; do not ingest")
    p.add_argument("--max-per-table", type=int, default=500, help="Max rows to ingest per table")
    p.add_argument("--min-rows", type=int, default=1, help="Skip tables with fewer rows than this")
    p.add_argument("--max-rows", type=int, default=200_000, help="Skip tables with more rows than this")
    p.add_argument("--only", default=None, help="Comma-separated list of tables to include (overrides skip list)")
    p.add_argument("--wide-text-only", action="store_true",
                   help="Only ingest tables with wide TEXT/VARCHAR columns (skip pure-scalar tables). "
                        "Default: ingest everything so ID/status/date lookups work too.")
    args = p.parse_args()

    parsed = urlparse(args.url)
    db_name = parsed.path.lstrip("/")
    if not db_name:
        print("ERROR: URL must include a database name (e.g. .../mydb)", file=sys.stderr)
        return 2
    db_label = re.sub(r"[^a-z0-9]+", "_", db_name.lower()).strip("_")[:40]

    only = None
    if args.only:
        only = {t.strip().lower() for t in args.only.split(",") if t.strip()}

    print(f"[introspect] connecting to {parsed.hostname}:{parsed.port or 3306}/{db_name}")
    engine = create_engine(args.url, pool_pre_ping=True)
    tables = introspect(engine, db_name)
    print(f"[introspect] found {len(tables)} base tables")

    plan = build_plan(tables, only=only, min_rows=args.min_rows, max_rows=args.max_rows,
                      embed_all_fields=not args.wide_text_only)
    print(f"[plan] {len(plan)} tables selected for ingest\n")
    header = f"{'table':<40} {'~rows':>8} {'pk':<18} {'title':<18} {'embed':>5} {'meta':>5}  wide/short"
    print(header)
    print("-" * len(header))
    for e in plan:
        print(f"{e['table']:<40} {e['row_count']:>8} {e['id_column']:<18} {e['title_column']:<18} "
              f"{len(e['text_columns']):>5} {len(e['extra_columns']):>5}  "
              f"{e['wide_count']}/{e['short_count']}")

    if args.dry_run:
        print("\n[dry-run] no ingest performed. Re-run without --dry-run to execute.")
        return 0

    print(f"\n[ingest] POSTing to {args.api_url} — max {args.max_per_table} rows per table")
    totals = {"tables_ok": 0, "tables_err": 0, "records": 0, "chunks": 0}
    t0 = time.time()
    for i, entry in enumerate(plan, 1):
        print(f"\n[{i}/{len(plan)}] {entry['table']} ...", end=" ", flush=True)
        try:
            res = ingest_table(entry, args.url, args.max_per_table, db_label, args.api_url)
            totals["tables_ok"] += 1
            totals["records"] += res.get("total_records_ingested", 0)
            totals["chunks"] += res.get("total_chunks", 0)
            n_err = len(res.get("errors") or [])
            print(f"OK   seen={res.get('total_records_seen')} ingested={res.get('total_records_ingested')} chunks={res.get('total_chunks')} errors={n_err}")
        except requests.HTTPError as ex:
            totals["tables_err"] += 1
            body = ex.response.text[:200] if ex.response is not None else ""
            print(f"HTTP {ex.response.status_code if ex.response is not None else '?'}  {body}")
        except Exception as ex:
            totals["tables_err"] += 1
            print(f"FAIL {type(ex).__name__}: {ex}")

    dt = time.time() - t0
    print(f"\n[done] tables_ok={totals['tables_ok']} tables_err={totals['tables_err']} "
          f"records={totals['records']} chunks={totals['chunks']} elapsed={dt:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
