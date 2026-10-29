# STEPVPN: сайт + SQL Server (база VPNDB из VPNDB.sql)
import re
import secrets
import uuid
from datetime import date, timedelta

from flask import Flask, request, redirect, render_template, url_for, session
from db import fetch_all, execute, execute_insert

app = Flask(__name__)
app.secret_key = "stepvpn-exam-secret"

# Таблицы для кабинета БД
TABLES = [
    (
        "plans", "Тарифы",
        "SELECT PlanId, Name, NameJp, Price, DurationDays, TrafficLimitGb, MaxDevices, IsTrial FROM Plans",
        "Plans", "PlanId",
        {
            "PlanId": "ID", "Name": "Название", "NameJp": "Срок", "Price": "Цена",
            "DurationDays": "Дней", "TrafficLimitGb": "Лимит ГБ",
            "MaxDevices": "Устройств", "IsTrial": "Пробный",
        },
        "Name",
    ),
    (
        "users", "Клиенты",
        "SELECT UserId, Email, FullName, IsActive FROM Users",
        "Users", "UserId",
        {"UserId": "ID", "Email": "Email", "FullName": "ФИО", "IsActive": "Активен"},
        "FullName",
    ),
    (
        "devices", "Устройства",
        "SELECT DeviceId, UserId, Name, Platform FROM Devices",
        "Devices", "DeviceId",
        {"DeviceId": "ID", "UserId": "ID клиента", "Name": "Имя", "Platform": "Платформа"},
        "Name",
    ),
    (
        "subscriptions", "Подписки",
        "SELECT SubscriptionId, UserId, PlanId, StartDate, EndDate, Status FROM Subscriptions",
        "Subscriptions", "SubscriptionId",
        {
            "SubscriptionId": "ID", "UserId": "ID клиента", "PlanId": "ID тарифа",
            "StartDate": "Начало", "EndDate": "Конец", "Status": "Статус (1-3)",
        },
        None,
    ),
    (
        "servers", "Серверы",
        "SELECT ServerId, Name, Country, City, PingMs, LoadPercent, IsOnline FROM Servers",
        "Servers", "ServerId",
        {
            "ServerId": "ID", "Name": "Имя", "Country": "Страна", "City": "Город",
            "PingMs": "Пинг", "LoadPercent": "Нагрузка %", "IsOnline": "Онлайн",
        },
        "Name",
    ),
    (
        "keys", "Ключи",
        "SELECT KeyId, UserId, ServerId, DeviceId, KeyCode, IsActive FROM AccessKeys",
        "AccessKeys", "KeyId",
        {
            "KeyId": "ID", "UserId": "ID клиента", "ServerId": "ID сервера",
            "DeviceId": "ID устройства", "KeyCode": "Ключ", "IsActive": "Активен",
        },
        None,
    ),
    (
        "sessions", "Сессии",
        "SELECT SessionId, KeyId, StartedAt, EndedAt, TrafficMb FROM Sessions",
        "Sessions", "SessionId",
        {
            "SessionId": "ID", "KeyId": "ID ключа", "StartedAt": "Старт",
            "EndedAt": "Конец", "TrafficMb": "Трафик МБ",
        },
        None,
    ),
]

# Отчёты JOIN для защиты
REPORTS = [
    (
        "Активные подписки",
        """
        SELECT u.FullName AS [Клиент], p.Name AS [Тариф], s.EndDate AS [До]
        FROM Subscriptions s
        JOIN Users u ON u.UserId = s.UserId
        JOIN Plans p ON p.PlanId = s.PlanId
        WHERE s.Status = 1
        ORDER BY s.EndDate
        """,
    ),
    (
        "Устройства клиентов",
        """
        SELECT u.FullName AS [Клиент], d.Name AS [Устройство], d.Platform AS [Платформа]
        FROM Devices d
        JOIN Users u ON u.UserId = d.UserId
        ORDER BY u.FullName
        """,
    ),
    (
        "Выручка по тарифам",
        """
        SELECT p.Name AS [Тариф], COUNT(s.SubscriptionId) AS [Подписок],
               p.Price * COUNT(s.SubscriptionId) AS [Сумма]
        FROM Plans p
        LEFT JOIN Subscriptions s ON s.PlanId = p.PlanId
        GROUP BY p.Name, p.Price
        ORDER BY [Сумма] DESC
        """,
    ),
    (
        "Серверы online",
        """
        SELECT Name AS [Сервер], Country AS [Страна], City AS [Город], PingMs AS [Пинг]
        FROM Servers WHERE IsOnline = 1 ORDER BY PingMs
        """,
    ),
]


def get_table(key):
    return next((x for x in TABLES if x[0] == key), None)


def as_dicts(cols, rows):
    return [dict(zip(cols, r)) for r in rows]


def get_plan(plan_id):
    cols, rows = fetch_all(
        "SELECT PlanId, Name, NameJp, Price, DurationDays, TrafficLimitGb, MaxDevices, IsTrial FROM Plans WHERE PlanId = ?",
        (plan_id,),
    )
    return dict(zip(cols, rows[0])) if rows else None


# Ключ для импорта в клиент
def make_stepvpn_key(server_name: str, city: str) -> str:
    uid = str(uuid.uuid4())
    tag = secrets.token_hex(3)
    host = f"{city.lower()}.stepvpn.net".replace(" ", "")
    return (
        f"vless://{uid}@{host}:443"
        f"?encryption=none&security=reality&type=tcp&fp=chrome"
        f"#{server_name}-{tag}"
    )


# --- Заказ: регистрация → оплата → запись в БД ---

@app.route("/order/<int:plan_id>", methods=["GET", "POST"])
def order_start(plan_id):
    plan = get_plan(plan_id)
    if not plan:
        return render_template(
            "error.html", title="Тариф не найден", message="Нет такого плана", back=url_for("index")
        ), 404

    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        platform = (request.form.get("platform") or "").strip()
        device_name = (request.form.get("device_name") or "").strip()
        values = request.form
        if not full_name or not email or not platform or not device_name:
            return render_template(
                "order_register.html", plan=plan, values=values, error="Заполни все поля"
            )
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            return render_template(
                "order_register.html", plan=plan, values=values, error="Некорректный email"
            )
        session["order_draft"] = {
            "plan_id": plan_id,
            "full_name": full_name,
            "email": email,
            "platform": platform,
            "device_name": device_name,
        }
        return redirect(url_for("order_pay", plan_id=plan_id))

    return render_template("order_register.html", plan=plan, values={}, error=None)


@app.route("/order/<int:plan_id>/pay", methods=["GET", "POST"])
def order_pay(plan_id):
    plan = get_plan(plan_id)
    draft = session.get("order_draft")
    if not plan or not draft or draft.get("plan_id") != plan_id:
        return redirect(url_for("order_start", plan_id=plan_id))

    if request.method == "POST":
        card = (request.form.get("card") or "").replace(" ", "")
        exp = (request.form.get("exp") or "").strip()
        cvc = (request.form.get("cvc") or "").strip()
        if len(card) < 12 or not exp or len(cvc) < 3:
            return render_template(
                "order_pay.html",
                plan=plan,
                draft=draft,
                values=request.form,
                error="Проверь данные карты (демо)",
            )

        _, existing = fetch_all("SELECT UserId FROM Users WHERE Email = ?", (draft["email"],))
        if existing:
            user_id = existing[0][0]
            execute(
                "UPDATE Users SET FullName = ?, IsActive = 1 WHERE UserId = ?",
                (draft["full_name"], user_id),
            )
        else:
            user_id = execute_insert(
                "INSERT INTO Users (Email, FullName, IsActive) VALUES (?, ?, 1)",
                (draft["email"], draft["full_name"]),
            )

        device_id = execute_insert(
            "INSERT INTO Devices (UserId, Name, Platform) VALUES (?, ?, ?)",
            (user_id, draft["device_name"], draft["platform"]),
        )

        start = date.today()
        end = start + timedelta(days=int(plan["DurationDays"]))
        subscription_id = execute_insert(
            "INSERT INTO Subscriptions (UserId, PlanId, StartDate, EndDate, Status) VALUES (?, ?, ?, ?, 1)",
            (user_id, plan_id, start.isoformat(), end.isoformat()),
        )

        scols, srows = fetch_all(
            "SELECT TOP 1 ServerId, Name, City FROM Servers WHERE IsOnline = 1 ORDER BY PingMs"
        )
        server = dict(zip(scols, srows[0]))
        stepvpn_key = make_stepvpn_key(server["Name"], server["City"])
        key_id = execute_insert(
            "INSERT INTO AccessKeys (UserId, ServerId, DeviceId, KeyCode, IsActive) VALUES (?, ?, ?, ?, 1)",
            (user_id, server["ServerId"], device_id, stepvpn_key),
        )

        session.pop("order_draft", None)
        session["order_result"] = {
            "user_name": draft["full_name"],
            "user_email": draft["email"],
            "plan_name": plan["Name"],
            "server_name": server["Name"],
            "city": server["City"],
            "stepvpn_key": stepvpn_key,
            "user_id": user_id,
            "device_id": device_id,
            "subscription_id": subscription_id,
            "key_id": key_id,
            "device_name": draft["device_name"],
            "platform": draft["platform"],
        }
        return redirect(url_for("order_success"))

    return render_template("order_pay.html", plan=plan, draft=draft, values={}, error=None)


@app.route("/order/success")
def order_success():
    result = session.get("order_result")
    if not result:
        return redirect(url_for("index"))
    return render_template("order_success.html", **result)


# --- Сайт ---

@app.route("/")
def index():
    plans = as_dicts(*fetch_all(
        "SELECT PlanId, Name, NameJp, Price, DurationDays, TrafficLimitGb, MaxDevices, IsTrial FROM Plans ORDER BY DurationDays, PlanId"
    ))
    for p in plans:
        n = int(p["Price"])
        p["PriceLabel"] = f"{n:,}".replace(",", " ")
    return render_template("index.html", plans=plans)


# --- Кабинет БД ---

@app.route("/admin")
@app.route("/db")
def db_page():
    tables = []
    for key, title, *_ in TABLES:
        name = get_table(key)[3]
        count = fetch_all(f"SELECT COUNT(*) FROM {name}")[1][0][0]
        tables.append({"key": key, "title": title, "sql_name": name, "count": count})
    return render_template("db.html", tables=tables)


@app.route("/reports")
def reports():
    items = []
    for title, sql in REPORTS:
        try:
            cols, rows = fetch_all(sql)
            items.append({"title": title, "cols": cols, "rows": rows, "error": None})
        except Exception as e:
            items.append({"title": title, "cols": [], "rows": [], "error": str(e)})
    return render_template("reports.html", reports=items)


@app.route("/t/<key>")
def view_table(key):
    t = get_table(key)
    if not t:
        return render_template(
            "error.html", title="Не найдено", message="Нет такой таблицы", back=url_for("db_page")
        ), 404
    _, title, sql, table, pk, labels, search_field = t
    search = request.args.get("q", "").strip()
    highlight = request.args.get("hl", type=int)
    params = ()
    if search and search_field:
        sql += f" WHERE {search_field} LIKE ?"
        params = (f"%{search}%",)
    sql += f" ORDER BY {pk} DESC" if pk else " ORDER BY 1"
    cols, rows = fetch_all(sql, params)
    return render_template(
        "table.html",
        key=key, title=title, cols=cols, rows=rows,
        labels=labels, pk=pk, search_field=search_field, search=search,
        highlight=highlight,
    )


@app.route("/del/<key>/<int:row_id>")
def delete(key, row_id):
    t = get_table(key)
    if not t or not t[4]:
        return render_template(
            "error.html", title="Нельзя", message="Удаление недоступно", back=url_for("db_page")
        ), 404
    _, _, _, table, pk, _, _ = t
    try:
        execute(f"DELETE FROM {table} WHERE {pk} = ?", (row_id,))
    except Exception as e:
        return render_template(
            "error.html", title="Ошибка", message=str(e), back=url_for("view_table", key=key)
        )
    return redirect(url_for("view_table", key=key))


@app.route("/add/<key>", methods=["GET", "POST"])
def add(key):
    t = get_table(key)
    if not t or not t[4]:
        return render_template(
            "error.html", title="Нельзя", message="Добавление недоступно", back=url_for("db_page")
        ), 404
    _, title, sql, table, pk, labels, _ = t
    empty_sql = sql.replace("SELECT", "SELECT TOP 0", 1)
    cols, _ = fetch_all(empty_sql)
    insert_cols = [c for c in cols if c != pk]

    if request.method == "POST":
        vals = [request.form.get(c, "") or None for c in insert_cols]
        placeholders = ", ".join("?" for _ in insert_cols)
        try:
            execute(
                f"INSERT INTO {table} ({', '.join(insert_cols)}) VALUES ({placeholders})",
                vals,
            )
            return redirect(url_for("view_table", key=key))
        except Exception as e:
            return render_template(
                "add.html", key=key, title=title, insert_cols=insert_cols,
                labels=labels, values=request.form, error=str(e),
            )

    return render_template(
        "add.html", key=key, title=title, insert_cols=insert_cols,
        labels=labels, values={}, error=None,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
