"""The Part 11 audit store — one append-only sqlite table per source PDF.

DESIGN.md L9 calls this "cheap to design in; brutal to retrofit." Every row is
an :class:`~usdm4_assure.contracts_audit.AuditRecord`; nothing is ever updated
or deleted. That is enforced twice over: the store exposes no update/delete
method, and the schema itself carries ``BEFORE UPDATE``/``BEFORE DELETE``
triggers that abort with an error, so even a stray hand-written ``UPDATE``
against the database file fails loudly instead of silently rewriting history.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from usdm4_assure.contracts_audit import AuditRecord, utc_now

_DEFAULT_DIR = Path("data/audit")

_TABLE = "audit_records"

# No explicit column types: SQLite's default (BLOB/"NONE") affinity stores
# whatever Python type is inserted as-is, so floats, ints and None round-trip
# exactly instead of being coerced to text (which a TEXT-affinity column would
# do). record_id is the primary key — one row per AuditRecord, ever.
_COLUMNS = AuditRecord.columns()

_APPEND_ONLY_MESSAGE = "audit records are append-only"


def _schema_sql() -> str:
    cols = ",\n    ".join(
        f"{c} TEXT PRIMARY KEY" if c == "record_id" else c
        for c in _COLUMNS
    )
    return f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
    {cols}
);

CREATE TRIGGER IF NOT EXISTS {_TABLE}_forbid_update
BEFORE UPDATE ON {_TABLE}
BEGIN
    SELECT RAISE(ABORT, '{_APPEND_ONLY_MESSAGE}');
END;

CREATE TRIGGER IF NOT EXISTS {_TABLE}_forbid_delete
BEFORE DELETE ON {_TABLE}
BEGIN
    SELECT RAISE(ABORT, '{_APPEND_ONLY_MESSAGE}');
END;
"""


def audit_dir(base_dir: str | Path | None = None) -> Path:
    """The directory audit databases live in: ``base_dir``, else ``USDM4_AUDIT_DIR``,
    else ``data/audit``. Shared by :func:`audit_path` and the review UI's source list."""
    return Path(base_dir or os.environ.get("USDM4_AUDIT_DIR", _DEFAULT_DIR))


def audit_path(source_sha256: str, base_dir: str | Path | None = None) -> Path:
    """The conventional path for a source PDF's audit database.

    Args:
        source_sha256: The source PDF's hex sha256 (its identity for auditing).
        base_dir: Override the directory. Defaults to ``data/audit`` or
            ``USDM4_AUDIT_DIR`` if set.
    """
    return audit_dir(base_dir) / f"{source_sha256}.sqlite"


def _source_pointer_path(source_sha256: str, base_dir: str | Path | None = None) -> Path:
    return audit_path(source_sha256, base_dir).with_suffix(".source.json")


def record_source(source_sha256: str, pdf_path: str | Path,
                  base_dir: str | Path | None = None) -> Path:
    """Remember which PDF a ``source_sha256`` audit database belongs to.

    The sqlite rows carry no filesystem path (an audit record documents a
    decision, not where the bytes live), but the review UI needs one to render
    a click-to-source crop. First write wins — the path a source was *first*
    audited under is what stays on record, even if a later run reads the same
    PDF from a different location.
    """
    path = _source_pointer_path(source_sha256, base_dir)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pdf_path": str(pdf_path), "recorded_at": utc_now()}, indent=2),
                    encoding="utf-8")
    return path


def read_source_pointer(source_sha256: str, base_dir: str | Path | None = None) -> dict | None:
    """The ``{"pdf_path", "recorded_at"}`` written by :func:`record_source`, or ``None``."""
    path = _source_pointer_path(source_sha256, base_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


class AuditStore:
    """An append-only store of :class:`AuditRecord` rows for one source PDF.

    Args:
        path: Database file location. If ``None``, ``source_sha256`` must be
            given and :func:`audit_path` derives the conventional path.
        source_sha256: The source PDF's sha256, used to derive ``path`` when
            ``path`` is not given directly.
    """

    def __init__(self, path: str | Path | None = None,
                 source_sha256: str | None = None) -> None:
        if path is None:
            if source_sha256 is None:
                raise ValueError("AuditStore requires either path or source_sha256")
            path = audit_path(source_sha256)
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_schema_sql())
        self._conn.commit()

    def append(self, record: AuditRecord) -> None:
        """Insert one record. There is deliberately no update/delete method."""
        row = record.to_row()
        placeholders = ", ".join("?" for _ in _COLUMNS)
        columns = ", ".join(_COLUMNS)
        self._conn.execute(
            f"INSERT INTO {_TABLE} ({columns}) VALUES ({placeholders})",
            [row[c] for c in _COLUMNS],
        )
        self._conn.commit()

    def read_all(self) -> list[AuditRecord]:
        """Every record, oldest first (insertion / rowid order)."""
        rows = self._conn.execute(
            f"SELECT * FROM {_TABLE} ORDER BY rowid"
        ).fetchall()
        return [AuditRecord.from_row(dict(r)) for r in rows]

    def read_field(self, domain: str, field: str) -> list[AuditRecord]:
        """Every record for one ``(domain, field)``, oldest first — the full
        history of a single field, including any later review edits."""
        rows = self._conn.execute(
            f"SELECT * FROM {_TABLE} WHERE domain = ? AND field = ? ORDER BY rowid",
            (domain, field),
        ).fetchall()
        return [AuditRecord.from_row(dict(r)) for r in rows]

    def __len__(self) -> int:
        row = self._conn.execute(f"SELECT COUNT(*) FROM {_TABLE}").fetchone()
        return row[0]

    def close(self) -> None:
        self._conn.close()
