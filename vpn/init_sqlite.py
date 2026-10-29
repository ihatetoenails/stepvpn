# Локальная инициализация vpn.db (SQLite), схема как VPNDB.sql
# Нужна, если SQL Server / ODBC недоступны на этом ПК.
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent / "vpn.db"

# DDL: таблицы + триггер журнала (время НЕ в Users)
SCHEMA = """
CREATE TABLE Plans (
    PlanId INTEGER PRIMARY KEY AUTOINCREMENT,
    Name TEXT NOT NULL,
    NameJp TEXT,
    Price REAL NOT NULL,
    DurationDays INTEGER NOT NULL,
    TrafficLimitGb INTEGER NOT NULL,
    MaxDevices INTEGER NOT NULL,
    IsTrial INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE Users (
    UserId INTEGER PRIMARY KEY AUTOINCREMENT,
    Email TEXT NOT NULL UNIQUE,
    FullName TEXT NOT NULL,
    IsActive INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE UserAuditLog (
    LogId INTEGER PRIMARY KEY AUTOINCREMENT,
    UserId INTEGER NOT NULL,
    FullName TEXT NOT NULL,
    AddedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TRIGGER trg_Users_AfterInsert
AFTER INSERT ON Users
BEGIN
    INSERT INTO UserAuditLog (UserId, FullName, AddedAt)
    VALUES (NEW.UserId, NEW.FullName, CURRENT_TIMESTAMP);
END;
CREATE TABLE Devices (
    DeviceId INTEGER PRIMARY KEY AUTOINCREMENT,
    UserId INTEGER NOT NULL REFERENCES Users(UserId) ON DELETE CASCADE,
    Name TEXT NOT NULL,
    Platform TEXT NOT NULL,
    AddedAt TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE Subscriptions (
    SubscriptionId INTEGER PRIMARY KEY AUTOINCREMENT,
    UserId INTEGER NOT NULL REFERENCES Users(UserId),
    PlanId INTEGER NOT NULL REFERENCES Plans(PlanId),
    StartDate TEXT NOT NULL,
    EndDate TEXT NOT NULL,
    Status INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE Servers (
    ServerId INTEGER PRIMARY KEY AUTOINCREMENT,
    Name TEXT NOT NULL,
    Country TEXT NOT NULL,
    City TEXT NOT NULL,
    FlagEmoji TEXT,
    IpAddress TEXT NOT NULL,
    PingMs INTEGER NOT NULL DEFAULT 50,
    LoadPercent INTEGER NOT NULL DEFAULT 0,
    IsOnline INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE AccessKeys (
    KeyId INTEGER PRIMARY KEY AUTOINCREMENT,
    UserId INTEGER NOT NULL REFERENCES Users(UserId),
    ServerId INTEGER NOT NULL REFERENCES Servers(ServerId),
    DeviceId INTEGER REFERENCES Devices(DeviceId),
    KeyCode TEXT NOT NULL UNIQUE,
    CreatedAt TEXT DEFAULT CURRENT_TIMESTAMP,
    IsActive INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE Sessions (
    SessionId INTEGER PRIMARY KEY AUTOINCREMENT,
    KeyId INTEGER NOT NULL REFERENCES AccessKeys(KeyId),
    StartedAt TEXT NOT NULL,
    EndedAt TEXT,
    TrafficMb INTEGER NOT NULL DEFAULT 0
);
"""


def main():
    """Пересоздать vpn.db и залить демо-данные (алгоритм заполнения)."""
    if DB.exists():
        DB.unlink()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.executescript(SCHEMA)

    cur.executemany(
        "INSERT INTO Plans (Name, NameJp, Price, DurationDays, TrafficLimitGb, MaxDevices, IsTrial) VALUES (?,?,?,?,?,?,?)",
        [
            ("Trial", "3 дня", 19, 3, 50, 1, 1),
            ("Plus", "1 месяц", 299, 30, 200, 3, 0),
            ("Pro", "6 месяцев", 1490, 180, 600, 5, 0),
            ("Year", "1 год", 2790, 365, 999, 10, 0),
        ],
    )
    cur.executemany(
        "INSERT INTO Users (Email, FullName, IsActive) VALUES (?,?,?)",
        [
            ("kenji@mail.ru", "Кенджи Сато", 1),
            ("yuki@mail.ru", "Юки Танака", 1),
            ("akira@mail.ru", "Акира Судзуки", 1),
            ("hana@mail.ru", "Хана Ватанабэ", 1),
            ("ryu@mail.ru", "Рю Накамура", 1),
            ("maria@mail.ru", "Мария Алиева", 1),
            ("blocked@mail.ru", "Тест Бан", 0),
        ],
    )
    cur.executemany(
        "INSERT INTO Devices (UserId, Name, Platform) VALUES (?,?,?)",
        [
            (1, "iPhone 15", "iOS"),
            (1, "PC Garage", "Windows"),
            (2, "Pixel 8", "Android"),
            (3, "MacBook Air", "macOS"),
            (3, "iPad Mini", "iOS"),
            (4, "Samsung S24", "Android"),
            (5, "STEPVPN Laptop", "Windows"),
            (6, "iPhone SE", "iOS"),
        ],
    )
    cur.executemany(
        "INSERT INTO Subscriptions (UserId, PlanId, StartDate, EndDate, Status) VALUES (?,?,?,?,?)",
        [
            (1, 2, "2026-09-01", "2026-10-01", 2),
            (1, 3, "2026-10-01", "2026-10-31", 1),
            (2, 1, "2026-10-26", "2026-10-29", 1),
            (3, 3, "2026-09-15", "2026-10-15", 1),
            (4, 4, "2026-01-01", "2027-01-01", 1),
            (5, 2, "2026-10-05", "2026-11-04", 1),
            (6, 2, "2026-08-01", "2026-08-31", 2),
            (6, 3, "2026-10-10", "2026-11-09", 1),
        ],
    )
    cur.executemany(
        "INSERT INTO Servers (Name, Country, City, FlagEmoji, IpAddress, PingMs, LoadPercent, IsOnline) VALUES (?,?,?,?,?,?,?,?)",
        [
            ("JP-Tokyo-01", "Япония", "Токио", "🇯🇵", "103.28.11.40", 22, 38, 1),
            ("JP-Osaka-01", "Япония", "Осака", "🇯🇵", "103.28.22.18", 28, 51, 1),
            ("DE-Frankfurt-01", "Германия", "Франкфурт", "🇩🇪", "45.10.20.31", 55, 62, 1),
            ("NL-Amsterdam-01", "Нидерланды", "Амстердам", "🇳🇱", "78.22.11.9", 50, 71, 1),
            ("US-NY-01", "США", "Нью-Йорк", "🇺🇸", "104.21.8.44", 140, 84, 1),
            ("TR-Istanbul-01", "Турция", "Стамбул", "🇹🇷", "185.12.7.90", 60, 12, 0),
        ],
    )
    cur.executemany(
        "INSERT INTO AccessKeys (UserId, ServerId, DeviceId, KeyCode, IsActive) VALUES (?,?,?,?,?)",
        [
            (1, 1, 1, "stepvpn-kenji-tyo-a1", 1),
            (1, 2, 2, "stepvpn-kenji-osk-b2", 1),
            (2, 1, 3, "stepvpn-yuki-tyo-c3", 1),
            (3, 3, 4, "stepvpn-akira-fra-d4", 1),
            (4, 1, 6, "stepvpn-hana-tyo-f6", 1),
            (5, 4, 7, "stepvpn-ryu-ams-g7", 1),
            (6, 2, 8, "stepvpn-maria-osk-h8", 1),
            (6, 1, None, "stepvpn-maria-old-x", 0),
        ],
    )
    cur.executemany(
        "INSERT INTO Sessions (KeyId, StartedAt, EndedAt, TrafficMb) VALUES (?,?,?,?)",
        [
            (1, "2026-10-20 08:00:00", "2026-10-20 09:30:00", 820),
            (1, "2026-10-21 18:00:00", "2026-10-21 20:10:00", 1450),
            (2, "2026-10-22 10:00:00", "2026-10-22 11:00:00", 310),
            (3, "2026-10-22 12:00:00", None, 95),
            (4, "2026-10-19 07:00:00", "2026-10-19 08:40:00", 1200),
            (5, "2026-10-23 15:00:00", "2026-10-23 16:20:00", 2400),
            (6, "2026-10-18 21:00:00", "2026-10-19 01:00:00", 3800),
            (7, "2026-10-24 09:00:00", "2026-10-24 09:45:00", 180),
        ],
    )
    conn.commit()
    conn.close()
    print(f"OK {DB}")


if __name__ == "__main__":
    main()
