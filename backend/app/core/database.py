"""
Database access for SQLite, PostgreSQL or SQL Server, chosen in backend/config/database.ini.

The rest of the app writes plain SQL with `?` placeholders and reads rows by column name;
this module translates placeholders for the active driver and returns dict-like rows.
On start, `init_db()` creates the tables from db/schema/<engine>.sql only if they do not exist, and
applies any db/schema/upgrades/<engine>_<version>_*.sql newer than the database's schema_version, once.
"""
import logging
import configparser
import json
import os
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.core.config import settings

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(_BACKEND_DIR, "config")
log = logging.getLogger("idp.db")
SCHEMA_DIR = os.path.join(_BACKEND_DIR, "db", "schema")
SCHEMA_VERSION = 5  # db/schema/upgrades/<engine>_00N_*.sql bring older databases up to this
ENGINES = ("sqlite", "postgresql", "sqlserver")


# ---------- settings ----------

def load_db_config() -> Dict[str, Any]:
    """Reads config/database.ini (created from the example on first start); environment variables win."""
    path = os.path.join(CONFIG_DIR, "database.ini")
    example = os.path.join(CONFIG_DIR, "database.example.ini")
    if not os.path.exists(path) and os.path.exists(example):
        shutil.copyfile(example, path)
    parser = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    parser.read(path)

    engine = (os.getenv("IDP_DB_ENGINE") or parser.get("database", "engine", fallback="sqlite")).strip().lower()
    if engine not in ENGINES:
        raise RuntimeError(f"Unknown database engine '{engine}' in config/database.ini. Use one of: {', '.join(ENGINES)}.")
    section = parser[engine] if parser.has_section(engine) else {}

    def val(key: str, default: str = "") -> str:
        return (os.getenv(f"IDP_DB_{key.upper()}") or section.get(key, default) or default).strip()

    cfg = {"engine": engine}
    if engine == "sqlite":
        p = val("path", "idp_saas.db")
        cfg["path"] = p if os.path.isabs(p) else os.path.join(settings.STORAGE_DIR, p)
    else:
        cfg.update(host=val("host"), port=val("port"), name=val("name"), user=val("user"),
                   password=val("password"), sslmode=val("sslmode", "prefer"))
    return cfg


DB_CONFIG = load_db_config()
DIALECT = DB_CONFIG["engine"]


def describe_db() -> str:
    """Where the app is connected, for logs. Never includes the password."""
    if DIALECT == "sqlite":
        return f"SQLite at {DB_CONFIG['path']}"
    return f"{DIALECT} database '{DB_CONFIG['name']}' on {DB_CONFIG['host']}{':' + DB_CONFIG['port'] if DB_CONFIG['port'] else ''} as {DB_CONFIG['user']}"


# ---------- connections ----------

class _Cursor:
    """Cursor with `?` placeholders on every engine, returning rows that read like dicts."""

    def __init__(self, raw, dialect: str):
        self._raw = raw
        self._dialect = dialect

    def execute(self, sql: str, params: Iterable[Any] = ()):
        params = tuple(params)
        if self._dialect != "sqlite":
            sql = sql.replace("?", "%s")
        if params:
            self._raw.execute(sql, params)
        else:
            self._raw.execute(sql)  # no placeholders to fill (and no "%" parsing on Postgres/SQL Server)
        return self

    def _row(self, r):
        if r is None or self._dialect == "sqlite":
            return r
        if isinstance(r, dict):
            return r
        return {d[0]: v for d, v in zip(self._raw.description, r)}

    def fetchone(self):
        return self._row(self._raw.fetchone())

    def fetchall(self) -> List[Any]:
        return [self._row(r) for r in self._raw.fetchall()]

    def fetchmany(self, n: int) -> List[Any]:
        return [self._row(r) for r in self._raw.fetchmany(n)]


class _Connection:
    def __init__(self, raw, dialect: str):
        self._raw = raw
        self._dialect = dialect

    def cursor(self) -> _Cursor:
        return _Cursor(self._raw.cursor(), self._dialect)

    def execute(self, sql: str, params: Iterable[Any] = ()) -> _Cursor:
        return self.cursor().execute(sql, params)

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()


def _raw_connection():
    c = DB_CONFIG
    if DIALECT == "sqlite":
        conn = sqlite3.connect(c["path"], timeout=30)
        conn.row_factory = sqlite3.Row
        return conn
    if DIALECT == "postgresql":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError:
            raise RuntimeError('PostgreSQL needs the psycopg driver: pip install "psycopg[binary]"')
        return psycopg.connect(host=c["host"], port=c["port"] or 5432, dbname=c["name"], user=c["user"],
                               password=c["password"], sslmode=c["sslmode"] or "prefer", row_factory=dict_row,
                               connect_timeout=15)
    try:
        import pymssql
    except ImportError:
        raise RuntimeError("SQL Server needs the pymssql driver: pip install pymssql")
    conn = pymssql.connect(server=c["host"], port=c["port"] or None, database=c["name"], user=c["user"],
                           password=c["password"], as_dict=True, login_timeout=15)
    cur = conn.cursor()
    cur.execute("SET QUOTED_IDENTIFIER ON")  # "user" and "timestamp" columns are quoted in queries
    return conn


def get_connection() -> _Connection:
    return _Connection(_raw_connection(), DIALECT)


# ---------- schema ----------

def _table_exists(conn: _Connection, name: str) -> bool:
    if DIALECT == "sqlite":
        sql = "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?"
    elif DIALECT == "postgresql":
        sql = "SELECT 1 FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = ?"
    else:
        sql = "SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?"
    return conn.execute(sql, (name,)).fetchone() is not None


def _schema_statements(path: Optional[str] = None) -> List[str]:
    with open(path or os.path.join(SCHEMA_DIR, f"{DIALECT}.sql"), encoding="utf-8") as f:
        text = f.read()
    if DIALECT == "sqlserver":
        parts = re.split(r"^\s*GO\s*$", text, flags=re.MULTILINE | re.IGNORECASE)
    else:
        text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("--"))
        parts = re.split(r";\s*$", text, flags=re.MULTILINE)
    return [p.strip() for p in parts if p.strip() and not all(l.strip().startswith("--") for l in p.strip().splitlines())]


def init_db():
    """
    Connects and, only when the tables are not there yet, creates them from the schema file and
    adds the built-in templates. A database that is already set up is left as it is.
    """
    log.info("Database: %s", describe_db())
    conn = get_connection()
    try:
        if _table_exists(conn, "schema_version"):
            _apply_upgrades(conn)  # already set up: only newer upgrade files, if any
            return
        for stmt in _schema_statements():
            conn.execute(stmt)
        conn.commit()
        log.info("Database tables created from db/schema/%s.sql", DIALECT)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    seed_defaults()
    conn = get_connection()
    conn.execute("INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                 (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()


def _apply_upgrades(conn: _Connection):
    """Runs each upgrade file newer than the database's schema version, in order, and records it."""
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    current = int(row["v"] or 0) if row else 0
    upgrades_dir = os.path.join(SCHEMA_DIR, "upgrades")
    files = sorted(f for f in os.listdir(upgrades_dir) if f.startswith(f"{DIALECT}_") and f.endswith(".sql")) \
        if os.path.isdir(upgrades_dir) else []
    for name in files:
        version = int(name[len(DIALECT) + 1:].split("_", 1)[0])
        if version <= current:
            continue
        for stmt in _schema_statements(os.path.join(upgrades_dir, name)):
            conn.execute(stmt)
        conn.execute("INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                     (version, datetime.now(timezone.utc).isoformat()))
        conn.commit()
        log.warning("Database upgraded to schema version %s (db/schema/upgrades/%s)", version, name)


def seed_defaults():
    """The built-in templates for contracts, identity documents and invoices."""
    now = datetime.now(timezone.utc).isoformat()
    templates = [
        ("schema-contract-std", "Legal Contract & NDA Analyzer", "contracts",
         "Standard extraction schema for commercial agreements, master service contracts, and mutual NDAs", [
             {"name": "agreement_title", "label": "Agreement Title", "data_type": "text", "required": True, "confidence_threshold": 0.8},
             {"name": "party_a", "label": "First Party (Disclosing/Client)", "data_type": "text", "required": True, "confidence_threshold": 0.85},
             {"name": "party_b", "label": "Second Party (Receiving/Vendor)", "data_type": "text", "required": True, "confidence_threshold": 0.85},
             {"name": "effective_date", "label": "Effective Date", "data_type": "date", "required": True, "confidence_threshold": 0.8},
             {"name": "expiration_date", "label": "Expiration / Term Date", "data_type": "date", "required": False, "confidence_threshold": 0.75},
             {"name": "governing_law", "label": "Governing Law / Jurisdiction", "data_type": "text", "required": True, "confidence_threshold": 0.8},
             {"name": "liability_cap", "label": "Liability Cap / Limitation", "data_type": "currency", "required": False, "confidence_threshold": 0.75},
             {"name": "confidentiality_term_years", "label": "Confidentiality Duration (Years)", "data_type": "number", "required": False, "confidence_threshold": 0.7},
             {"name": "termination_notice_days", "label": "Termination Notice (Days)", "data_type": "number", "required": False, "confidence_threshold": 0.7},
             {"name": "risk_rating", "label": "Overall Contract Risk Rating", "data_type": "enum", "enum_values": ["LOW", "MEDIUM", "HIGH"], "required": True, "confidence_threshold": 0.85},
         ]),
        ("schema-identity-std", "Global Passport & ID Document Verifier", "identity",
         "KYC-compliant identity document parser with ICAO 9303 MRZ checksum validation", [
             {"name": "document_type", "label": "Document Type", "data_type": "enum", "enum_values": ["PASSPORT", "DRIVERS_LICENSE", "NATIONAL_ID"], "required": True, "confidence_threshold": 0.9},
             {"name": "full_name", "label": "Full Legal Name", "data_type": "text", "required": True, "confidence_threshold": 0.88},
             {"name": "document_number", "label": "Document / Passport Number", "data_type": "text", "required": True, "confidence_threshold": 0.92},
             {"name": "issuing_country", "label": "Issuing Country (ISO Code)", "data_type": "text", "required": True, "confidence_threshold": 0.9},
             {"name": "nationality", "label": "Nationality", "data_type": "text", "required": True, "confidence_threshold": 0.88},
             {"name": "date_of_birth", "label": "Date of Birth", "data_type": "date", "required": True, "confidence_threshold": 0.9},
             {"name": "date_of_expiry", "label": "Expiration Date", "data_type": "date", "required": True, "confidence_threshold": 0.9},
             {"name": "sex", "label": "Sex / Gender", "data_type": "enum", "enum_values": ["M", "F", "X"], "required": False, "confidence_threshold": 0.85},
             {"name": "mrz_checksum_valid", "label": "MRZ Checksum Verified", "data_type": "enum", "enum_values": ["PASS", "FAIL"], "required": True, "confidence_threshold": 0.95},
         ]),
        ("schema-invoice-std", "Automated Invoice & Accounts Payable", "invoices",
         "Extracts invoice headers, vendor details, and performs mathematical reconciliation", [
             {"name": "invoice_number", "label": "Invoice Number", "data_type": "text", "required": True, "confidence_threshold": 0.9},
             {"name": "vendor_name", "label": "Vendor / Supplier Name", "data_type": "text", "required": True, "confidence_threshold": 0.85},
             {"name": "invoice_date", "label": "Invoice Date", "data_type": "date", "required": True, "confidence_threshold": 0.85},
             {"name": "due_date", "label": "Payment Due Date", "data_type": "date", "required": False, "confidence_threshold": 0.8},
             {"name": "currency", "label": "Currency", "data_type": "enum", "enum_values": ["USD", "EUR", "GBP", "CAD", "AUD"], "required": True, "confidence_threshold": 0.9},
             {"name": "subtotal", "label": "Subtotal Amount", "data_type": "currency", "required": True, "confidence_threshold": 0.9},
             {"name": "tax_amount", "label": "Tax / VAT Amount", "data_type": "currency", "required": False, "confidence_threshold": 0.85},
             {"name": "total_amount", "label": "Total Amount", "data_type": "currency", "required": True, "confidence_threshold": 0.95},
             {"name": "math_check_valid", "label": "Math Integrity (Subtotal + Tax == Total)", "data_type": "enum", "enum_values": ["VALID", "DISCREPANCY", "UNVERIFIED"], "required": True, "confidence_threshold": 0.95},
         ]),
    ]
    conn = get_connection()
    for tid, name, code, desc, fields in templates:
        if not conn.execute("SELECT 1 FROM custom_schemas WHERE id = ?", (tid,)).fetchone():
            conn.execute("""
                INSERT INTO custom_schemas (id, name, document_type_code, description, fields_json, created_at, updated_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """, (tid, name, code, desc, json.dumps(fields), now, now))
    conn.commit()
    conn.close()
