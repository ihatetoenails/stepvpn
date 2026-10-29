# Подключение к Microsoft SQL Server, база VPNDB.
# Сначала выполни VPNDB.sql в SSMS. Имя сервера — как при подключении в SSMS.
import pyodbc

CONN_STR = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=NOUT;"  # ← замени на своё имя сервера из SSMS
    "DATABASE=VPNDB;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)


def get_conn():
    return pyodbc.connect(CONN_STR)


def fetch_all(query, params=()):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        cols = [c[0] for c in cur.description] if cur.description else []
        return cols, cur.fetchall()


def execute(query, params=()):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        return cur.rowcount


def execute_insert(query, params=()):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        cur.execute("SELECT CAST(SCOPE_IDENTITY() AS INT)")
        row_id = cur.fetchone()[0]
        conn.commit()
        return row_id
