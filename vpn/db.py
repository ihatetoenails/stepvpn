# =============================================================================
# db.py — слой доступа к базе данных
# На экзамене: Microsoft SQL Server (VPNDB.sql в SSMS).
# Дома: если ODBC/сервер нет — автоматически SQLite (vpn.db).
# =============================================================================
import os
import re
import sqlite3
from pathlib import Path

# Файл локальной БД (только режим sqlite)
DB_PATH = Path(__file__).resolve().parent / "vpn.db"

# Строка подключения к SQL Server — SERVER как в окне входа SSMS
SQLSERVER_CONN = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    f"SERVER={os.environ.get('STEPVPN_SERVER', 'NOUT')};"
    "DATABASE=VPNDB;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

# Текущий бэкенд: "mssql" или "sqlite" (выбирается один раз)
_backend = None


def _try_mssql():
    """Проверить, доступен ли SQL Server + ODBC Driver 18."""
    try:
        import pyodbc
        conn = pyodbc.connect(SQLSERVER_CONN, timeout=3)
        conn.close()
        return True
    except Exception:
        return False


def get_backend():
    """Вернуть 'mssql' или 'sqlite' (с автоопределением)."""
    global _backend
    if _backend is None:
        force = os.environ.get("STEPVPN_BACKEND", "").strip().lower()
        if force in ("mssql", "sqlite"):
            _backend = force
        else:
            _backend = "mssql" if _try_mssql() else "sqlite"
        print(f"[db] backend = {_backend}")
    return _backend


def get_conn():
    """Открыть соединение с выбранным бэкендом."""
    if get_backend() == "mssql":
        import pyodbc
        return pyodbc.connect(SQLSERVER_CONN)
    if not DB_PATH.exists():
        from init_sqlite import main as init_db
        init_db()
    return sqlite3.connect(DB_PATH)


def _to_sqlite(query: str) -> str:
    """Адаптировать T-SQL куски под SQLite (TOP, [alias], TVF)."""
    q = re.sub(r"\[([^\]]+)\]", r'"\1"', query)
    # Табличная функция → обычный SELECT с теми же 2 параметрами
    q = re.sub(
        r"SELECT\s+\*\s+FROM\s+dbo\.fn_FilterServers\s*\(\s*\?\s*,\s*\?\s*\)",
        "SELECT ServerId, Name, Country, City, FlagEmoji, IpAddress, PingMs, LoadPercent, IsOnline "
        "FROM Servers WHERE Country = ? AND IsOnline = ?",
        q,
        flags=re.IGNORECASE,
    )
    m = re.search(r"SELECT\s+TOP\s+(\d+)\s+", q, flags=re.IGNORECASE)
    if m:
        n = m.group(1)
        q = re.sub(r"SELECT\s+TOP\s+\d+\s+", "SELECT ", q, count=1, flags=re.IGNORECASE)
        if "LIMIT" not in q.upper():
            q = q.rstrip().rstrip(";") + f" LIMIT {n}"
    return q


def fetch_all(query, params=()):
    """SELECT: вернуть (список имён колонок, список строк)."""
    with get_conn() as conn:
        cur = conn.cursor()
        q = query if get_backend() == "mssql" else _to_sqlite(query)
        cur.execute(q, params)
        cols = [c[0] for c in cur.description] if cur.description else []
        return cols, cur.fetchall()


def execute(query, params=()):
    """UPDATE / DELETE / INSERT без возврата ID."""
    with get_conn() as conn:
        cur = conn.cursor()
        q = query if get_backend() == "mssql" else _to_sqlite(query)
        cur.execute(q, params)
        conn.commit()
        return cur.rowcount


def execute_insert(query, params=()):
    """INSERT и вернуть новый IDENTITY / lastrowid."""
    with get_conn() as conn:
        cur = conn.cursor()
        q = query if get_backend() == "mssql" else _to_sqlite(query)
        cur.execute(q, params)
        if get_backend() == "mssql":
            cur.execute("SELECT CAST(SCOPE_IDENTITY() AS INT)")
            row_id = cur.fetchone()[0]
        else:
            row_id = cur.lastrowid
        conn.commit()
        return row_id
