"""SQLite persistence for current shipment records, upload history and immutable upload snapshots."""
from __future__ import annotations
import sqlite3, json, hashlib
from pathlib import Path
import pandas as pd

DB_PATH = Path(__file__).resolve().parent / "data" / "quiklee.db"


def connect(db_path: Path | str = DB_PATH):
    path=Path(db_path); path.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path: Path | str = DB_PATH):
    with connect(db_path) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS brand_registry (\n          brand TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);\n        CREATE TABLE IF NOT EXISTS shipments_current (
          brand TEXT NOT NULL, shipment_id TEXT NOT NULL, manifested_date TEXT,
          shipment_status TEXT, courier_name TEXT, drop_location_state TEXT,
          record_json TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (brand, shipment_id));
        CREATE TABLE IF NOT EXISTS upload_batches (
          batch_id INTEGER PRIMARY KEY AUTOINCREMENT, brand TEXT NOT NULL,
          reporting_date TEXT NOT NULL, filename TEXT NOT NULL, file_sha256 TEXT NOT NULL,
          row_count INTEGER NOT NULL, imported_count INTEGER NOT NULL,
          issue_count INTEGER NOT NULL, uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (brand, reporting_date, file_sha256));
        CREATE TABLE IF NOT EXISTS shipment_snapshots (
          snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id INTEGER NOT NULL,
          brand TEXT NOT NULL, reporting_date TEXT NOT NULL, shipment_id TEXT NOT NULL,
          record_json TEXT NOT NULL,
          FOREIGN KEY(batch_id) REFERENCES upload_batches(batch_id));
        CREATE INDEX IF NOT EXISTS idx_current_manifested ON shipments_current(manifested_date);
        CREATE INDEX IF NOT EXISTS idx_snapshots_date ON shipment_snapshots(brand, reporting_date);
        ''')


DEFAULT_BRANDS = ["Freely", "Kotart", "BigBearFarms"]


def list_brands(db_path: Path | str = DB_PATH) -> list[str]:
    """Return registered brand names in stable insertion order."""
    with connect(db_path) as c:
        c.executemany(
            "INSERT OR IGNORE INTO brand_registry(brand) VALUES(?)",
            [(brand,) for brand in DEFAULT_BRANDS],
        )
        rows = c.execute(
            "SELECT brand FROM brand_registry ORDER BY created_at, brand COLLATE NOCASE"
        ).fetchall()
    stored = [row[0] for row in rows]
    return DEFAULT_BRANDS.copy() + [b for b in stored if b not in DEFAULT_BRANDS]


def add_brand(brand: str, db_path: Path | str = DB_PATH) -> tuple[bool, str]:
    """Register a new brand name. Returns (created, canonical_name)."""
    name = " ".join(str(brand).strip().split())
    if not name:
        raise ValueError("Enter a brand name.")
    if len(name) > 80:
        raise ValueError("Brand name must be 80 characters or fewer.")
    existing = {b.casefold(): b for b in list_brands(db_path)}
    if name.casefold() in existing:
        return False, existing[name.casefold()]
    with connect(db_path) as c:
        c.execute("INSERT INTO brand_registry(brand) VALUES(?)", (name,))
    return True, name


def _json_value(v):
    if pd.isna(v): return None
    if isinstance(v, (pd.Timestamp,)): return v.isoformat()
    if hasattr(v, "item"):
        try: return v.item()
        except Exception: pass
    return v


def _row_json(row: pd.Series) -> str:
    return json.dumps({str(k):_json_value(v) for k,v in row.items()}, ensure_ascii=False, default=str)


def upsert_current(df: pd.DataFrame, db_path: Path | str = DB_PATH) -> int:
    if df.empty: return 0
    rows=[]
    for _,r in df.iterrows():
        sid=str(r.get("shipment_id", "")).strip()
        if not sid: continue
        md=r.get("manifested_date")
        rows.append((str(r["Brand"]),sid,md.isoformat() if pd.notna(md) else None,str(r.get("shipment_status","Unknown")),str(r.get("courier_name","Unknown")),str(r.get("drop_location_state","Unknown")),_row_json(r)))
    with connect(db_path) as c:
        c.executemany('''INSERT INTO shipments_current(brand,shipment_id,manifested_date,shipment_status,courier_name,drop_location_state,record_json)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(brand,shipment_id) DO UPDATE SET manifested_date=excluded.manifested_date,shipment_status=excluded.shipment_status,courier_name=excluded.courier_name,drop_location_state=excluded.drop_location_state,record_json=excluded.record_json,updated_at=CURRENT_TIMESTAMP''',rows)
    return len(rows)


def import_upload(df: pd.DataFrame, brand: str, reporting_date, filename: str, file_bytes: bytes, issue_count: int, db_path: Path | str = DB_PATH) -> dict:
    sha=hashlib.sha256(file_bytes).hexdigest(); report_date=pd.Timestamp(reporting_date).date().isoformat()
    with connect(db_path) as c:
        old=c.execute("SELECT batch_id FROM upload_batches WHERE brand=? AND reporting_date=? AND file_sha256=?",(brand,report_date,sha)).fetchone()
        if old:
            return {"duplicate_upload":True,"batch_id":old[0],"imported_count":0}
        cur=c.execute("INSERT INTO upload_batches(brand,reporting_date,filename,file_sha256,row_count,imported_count,issue_count) VALUES(?,?,?,?,?,?,?)",(brand,report_date,filename,sha,len(df),0,issue_count))
        batch_id=cur.lastrowid
        snap=[]
        for _,r in df.iterrows():
            sid=str(r.get("shipment_id", "")).strip()
            if sid:
                snap.append((batch_id,brand,report_date,sid,_row_json(r)))
        c.executemany("INSERT INTO shipment_snapshots(batch_id,brand,reporting_date,shipment_id,record_json) VALUES(?,?,?,?,?)",snap)
        c.execute("UPDATE upload_batches SET imported_count=? WHERE batch_id=?",(len(snap),batch_id))
    n=upsert_current(df,db_path)
    return {"duplicate_upload":False,"batch_id":batch_id,"imported_count":n}


def load_current(db_path: Path | str = DB_PATH) -> pd.DataFrame:
    with connect(db_path) as c:
        rows=c.execute("SELECT record_json FROM shipments_current").fetchall()
    if not rows: return pd.DataFrame()
    df=pd.DataFrame([json.loads(r[0]) for r in rows])
    for col in ["manifested_date","manifest_date","latest_status_date","delivery_date","delivery_rto_date","pickup_date","edd","pdd","first_attempt_date"]:
        if col in df: df[col]=pd.to_datetime(df[col],errors="coerce")
    for col in ["tat","attempt_count","pickup_attempts","rto_attempts","est_shipping_charge","cod_amount","total_amount","tat_breached"]:
        if col in df: df[col]=pd.to_numeric(df[col],errors="coerce")
    return df


def upload_history(db_path: Path | str = DB_PATH) -> pd.DataFrame:
    with connect(db_path) as c:
        return pd.read_sql_query("SELECT batch_id,brand,reporting_date,filename,row_count,imported_count,issue_count,uploaded_at FROM upload_batches ORDER BY uploaded_at DESC",c)


def load_snapshot(reporting_date, brand: str | None = None, db_path: Path | str = DB_PATH) -> pd.DataFrame:
    """Load immutable uploaded records for a reporting date; optionally restrict to one brand."""
    report_date=pd.Timestamp(reporting_date).date().isoformat()
    query="SELECT record_json FROM shipment_snapshots WHERE reporting_date=?"
    params=[report_date]
    if brand:
        query += " AND brand=?"; params.append(brand)
    query += " ORDER BY snapshot_id"
    with connect(db_path) as c:
        rows=c.execute(query,params).fetchall()
    if not rows: return pd.DataFrame()
    df=pd.DataFrame([json.loads(r[0]) for r in rows])
    for col in ["manifested_date","manifest_date","latest_status_date","delivery_rto_date","pickup_date","edd","pdd","first_attempt_date"]:
        if col in df: df[col]=pd.to_datetime(df[col],errors="coerce")
    for col in ["tat","attempt_count","pickup_attempts","rto_attempts","est_shipping_charge","cod_amount","total_amount","tat_breached"]:
        if col in df: df[col]=pd.to_numeric(df[col],errors="coerce")
    return df
