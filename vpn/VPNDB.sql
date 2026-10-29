/* STEPVPN — учебная БД (Microsoft SQL Server / SSMS)
   Критерии:
   - табличная функция с 2 параметрами
   - алгоритм заполнения БД
   - алгоритм фильтрации
   - триггер журнала пользователей (время НЕ в Users)
*/

USE master;
GO

IF DB_ID('VPNDB') IS NOT NULL
BEGIN
    ALTER DATABASE VPNDB SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE VPNDB;
END
GO

CREATE DATABASE VPNDB;
GO

USE VPNDB;
GO

/*
  Схема:
  Users → Subscriptions → Plans
  Users → Devices
  Users → AccessKeys → Servers → Sessions
  Users → (триггер) → UserAuditLog

  Status подписки: 1=активна, 2=истекла, 3=отменена
*/

/* ---------- 1. ТАБЛИЦЫ ---------- */

/* Тарифы */
CREATE TABLE Plans (
    PlanId          INT IDENTITY(1,1) PRIMARY KEY,
    Name            NVARCHAR(100) NOT NULL,
    NameJp          NVARCHAR(100) NULL,   -- подпись срока («1 месяц»)
    Price           DECIMAL(18,2) NOT NULL CHECK (Price >= 0),
    DurationDays    INT NOT NULL CHECK (DurationDays > 0),
    TrafficLimitGb  INT NOT NULL CHECK (TrafficLimitGb > 0),
    MaxDevices      INT NOT NULL CHECK (MaxDevices > 0),
    IsTrial         BIT NOT NULL DEFAULT 0
);
GO

/* Клиенты — время регистрации здесь НЕ хранится (требование экзамена) */
CREATE TABLE Users (
    UserId          INT IDENTITY(1,1) PRIMARY KEY,
    Email           NVARCHAR(150) NOT NULL UNIQUE,
    FullName        NVARCHAR(150) NOT NULL,
    IsActive        BIT NOT NULL DEFAULT 1
);
GO

/* Журнал: id, имя и время добавления пользователя (пишет триггер) */
CREATE TABLE UserAuditLog (
    LogId           INT IDENTITY(1,1) PRIMARY KEY,
    UserId          INT NOT NULL,
    FullName        NVARCHAR(150) NOT NULL,
    AddedAt         DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

/* Устройства */
CREATE TABLE Devices (
    DeviceId        INT IDENTITY(1,1) PRIMARY KEY,
    UserId          INT NOT NULL,
    Name            NVARCHAR(100) NOT NULL,
    Platform        NVARCHAR(50) NOT NULL,
    AddedAt         DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_Devices_Users FOREIGN KEY (UserId) REFERENCES Users(UserId) ON DELETE CASCADE
);
GO

/* Подписки */
CREATE TABLE Subscriptions (
    SubscriptionId  INT IDENTITY(1,1) PRIMARY KEY,
    UserId          INT NOT NULL,
    PlanId          INT NOT NULL,
    StartDate       DATE NOT NULL,
    EndDate         DATE NOT NULL,
    Status          TINYINT NOT NULL DEFAULT 1,
    CONSTRAINT FK_Subscriptions_Users FOREIGN KEY (UserId) REFERENCES Users(UserId),
    CONSTRAINT FK_Subscriptions_Plans FOREIGN KEY (PlanId) REFERENCES Plans(PlanId),
    CONSTRAINT CK_Subscriptions_Dates CHECK (EndDate >= StartDate)
);
GO

/* Серверы */
CREATE TABLE Servers (
    ServerId        INT IDENTITY(1,1) PRIMARY KEY,
    Name            NVARCHAR(100) NOT NULL,
    Country         NVARCHAR(100) NOT NULL,
    City            NVARCHAR(100) NOT NULL,
    FlagEmoji       NVARCHAR(8) NULL,
    IpAddress       NVARCHAR(45) NOT NULL,
    PingMs          INT NOT NULL DEFAULT 50 CHECK (PingMs >= 0),
    LoadPercent     INT NOT NULL DEFAULT 0 CHECK (LoadPercent BETWEEN 0 AND 100),
    IsOnline        BIT NOT NULL DEFAULT 1
);
GO

/* Ключи доступа */
CREATE TABLE AccessKeys (
    KeyId           INT IDENTITY(1,1) PRIMARY KEY,
    UserId          INT NOT NULL,
    ServerId        INT NOT NULL,
    DeviceId        INT NULL,
    KeyCode         NVARCHAR(500) NOT NULL UNIQUE,
    CreatedAt       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    IsActive        BIT NOT NULL DEFAULT 1,
    CONSTRAINT FK_AccessKeys_Users FOREIGN KEY (UserId) REFERENCES Users(UserId),
    CONSTRAINT FK_AccessKeys_Servers FOREIGN KEY (ServerId) REFERENCES Servers(ServerId),
    CONSTRAINT FK_AccessKeys_Devices FOREIGN KEY (DeviceId) REFERENCES Devices(DeviceId)
);
GO

/* Сессии */
CREATE TABLE Sessions (
    SessionId       INT IDENTITY(1,1) PRIMARY KEY,
    KeyId           INT NOT NULL,
    StartedAt       DATETIME2 NOT NULL,
    EndedAt         DATETIME2 NULL,
    TrafficMb       INT NOT NULL DEFAULT 0 CHECK (TrafficMb >= 0),
    CONSTRAINT FK_Sessions_AccessKeys FOREIGN KEY (KeyId) REFERENCES AccessKeys(KeyId),
    CONSTRAINT CK_Sessions_Dates CHECK (EndedAt IS NULL OR EndedAt >= StartedAt)
);
GO

/* ---------- 2. ТРИГГЕР ---------- */
/*
  После INSERT в Users сохраняет UserId, FullName и время в UserAuditLog.
  В таблице Users поля времени нет.
*/
CREATE TRIGGER trg_Users_AfterInsert
ON Users
AFTER INSERT
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO UserAuditLog (UserId, FullName, AddedAt)
    SELECT i.UserId, i.FullName, SYSUTCDATETIME()
    FROM inserted AS i;
END
GO

/* ---------- 3. ТАБЛИЧНАЯ ФУНКЦИЯ (2 параметра) ---------- */
/*
  fn_FilterServers(@Country, @IsOnline)
  Возвращает серверы, отфильтрованные по стране И по статусу online/offline.
  Пример: SELECT * FROM dbo.fn_FilterServers(N'Япония', 1);
*/
CREATE FUNCTION dbo.fn_FilterServers
(
    @Country  NVARCHAR(100),
    @IsOnline BIT
)
RETURNS TABLE
AS
RETURN
(
    SELECT
        ServerId,
        Name,
        Country,
        City,
        FlagEmoji,
        IpAddress,
        PingMs,
        LoadPercent,
        IsOnline
    FROM Servers
    WHERE Country = @Country
      AND IsOnline = @IsOnline
);
GO

/* ---------- 4. АЛГОРИТМ ЗАПОЛНЕНИЯ БД ---------- */
/*
  Алгоритм заполнения (порядок важен из‑за FK):

  Шаг 1. INSERT Plans          — справочник тарифов (нет зависимостей)
  Шаг 2. INSERT Users          — клиенты; триггер сразу пишет UserAuditLog
  Шаг 3. INSERT Devices        — устройства (нужен UserId)
  Шаг 4. INSERT Subscriptions  — подписки (нужны UserId + PlanId)
  Шаг 5. INSERT Servers        — локации (нет зависимостей от клиентов)
  Шаг 6. INSERT AccessKeys     — ключи (UserId + ServerId + DeviceId)
  Шаг 7. INSERT Sessions       — сессии (нужен KeyId)

  Сайт Flask после оплаты повторяет шаги 2–4 и 6 для нового заказа.
*/

/* Данные: тарифы */
INSERT INTO Plans (Name, NameJp, Price, DurationDays, TrafficLimitGb, MaxDevices, IsTrial) VALUES
(N'Trial', N'3 дня',       19.00,    3,  50,  1, 1),
(N'Plus',  N'1 месяц',    299.00,   30, 200,  3, 0),
(N'Pro',   N'6 месяцев', 1490.00,  180, 600,  5, 0),
(N'Year',  N'1 год',     2790.00,  365, 999, 10, 0);
GO

/* Данные: клиенты (триггер заполнит UserAuditLog) */
INSERT INTO Users (Email, FullName, IsActive) VALUES
(N'kenji@mail.ru',   N'Кенджи Сато',   1),
(N'yuki@mail.ru',    N'Юки Танака',    1),
(N'akira@mail.ru',   N'Акира Судзуки', 1),
(N'hana@mail.ru',    N'Хана Ватанабэ', 1),
(N'ryu@mail.ru',     N'Рю Накамура',   1),
(N'maria@mail.ru',   N'Мария Алиева',  1),
(N'blocked@mail.ru', N'Тест Бан',      0);
GO

/* Данные: устройства */
INSERT INTO Devices (UserId, Name, Platform) VALUES
(1, N'iPhone 15',      N'iOS'),
(1, N'PC Garage',      N'Windows'),
(2, N'Pixel 8',        N'Android'),
(3, N'MacBook Air',    N'macOS'),
(3, N'iPad Mini',      N'iOS'),
(4, N'Samsung S24',    N'Android'),
(5, N'STEPVPN Laptop', N'Windows'),
(6, N'iPhone SE',      N'iOS');
GO

/* Данные: подписки */
INSERT INTO Subscriptions (UserId, PlanId, StartDate, EndDate, Status) VALUES
(1, 2, '2026-09-01', '2026-10-01', 2),
(1, 3, '2026-10-01', '2026-10-31', 1),
(2, 1, '2026-10-26', '2026-10-29', 1),
(3, 3, '2026-09-15', '2026-10-15', 1),
(4, 4, '2026-01-01', '2027-01-01', 1),
(5, 2, '2026-10-05', '2026-11-04', 1),
(6, 2, '2026-08-01', '2026-08-31', 2),
(6, 3, '2026-10-10', '2026-11-09', 1);
GO

/* Данные: серверы */
INSERT INTO Servers (Name, Country, City, FlagEmoji, IpAddress, PingMs, LoadPercent, IsOnline) VALUES
(N'JP-Tokyo-01',     N'Япония',     N'Токио',     N'🇯🇵', '103.28.11.40',  22, 38, 1),
(N'JP-Osaka-01',     N'Япония',     N'Осака',     N'🇯🇵', '103.28.22.18',  28, 51, 1),
(N'DE-Frankfurt-01', N'Германия',   N'Франкфурт', N'🇩🇪', '45.10.20.31',   55, 62, 1),
(N'NL-Amsterdam-01', N'Нидерланды', N'Амстердам', N'🇳🇱', '78.22.11.9',    50, 71, 1),
(N'US-NY-01',        N'США',        N'Нью-Йорк',  N'🇺🇸', '104.21.8.44',  140, 84, 1),
(N'TR-Istanbul-01',  N'Турция',     N'Стамбул',   N'🇹🇷', '185.12.7.90',   60, 12, 0);
GO

/* Данные: ключи */
INSERT INTO AccessKeys (UserId, ServerId, DeviceId, KeyCode, IsActive) VALUES
(1, 1, 1, N'stepvpn-kenji-tyo-a1', 1),
(1, 2, 2, N'stepvpn-kenji-osk-b2', 1),
(2, 1, 3, N'stepvpn-yuki-tyo-c3',  1),
(3, 3, 4, N'stepvpn-akira-fra-d4', 1),
(4, 1, 6, N'stepvpn-hana-tyo-f6',  1),
(5, 4, 7, N'stepvpn-ryu-ams-g7',   1),
(6, 2, 8, N'stepvpn-maria-osk-h8', 1),
(6, 1, NULL, N'stepvpn-maria-old-x', 0);
GO

/* Данные: сессии */
INSERT INTO Sessions (KeyId, StartedAt, EndedAt, TrafficMb) VALUES
(1, '2026-10-20 08:00:00', '2026-10-20 09:30:00', 820),
(1, '2026-10-21 18:00:00', '2026-10-21 20:10:00', 1450),
(2, '2026-10-22 10:00:00', '2026-10-22 11:00:00', 310),
(3, '2026-10-22 12:00:00', NULL,                    95),
(4, '2026-10-19 07:00:00', '2026-10-19 08:40:00', 1200),
(5, '2026-10-23 15:00:00', '2026-10-23 16:20:00', 2400),
(6, '2026-10-18 21:00:00', '2026-10-19 01:00:00', 3800),
(7, '2026-10-24 09:00:00', '2026-10-24 09:45:00', 180);
GO

/* ---------- 5. АЛГОРИТМ ФИЛЬТРАЦИИ ---------- */
/*
  Алгоритм фильтрации серверов:

  1. Пользователь задаёт два параметра: Country (страна) и IsOnline (0/1).
  2. Вызывается табличная функция:
       SELECT * FROM dbo.fn_FilterServers(@Country, @IsOnline);
  3. Функция читает Servers и оставляет строки, где
       Country = @Country AND IsOnline = @IsOnline.
  4. Результат — таблица (можно JOIN дальше или показать на сайте /filter).

  Проверка в SSMS:
*/
SELECT * FROM dbo.fn_FilterServers(N'Япония', 1);
GO

/* Контрольные COUNT */
SELECT 'Plans' AS Таблица, COUNT(*) AS Записей FROM Plans
UNION ALL SELECT 'Users', COUNT(*) FROM Users
UNION ALL SELECT 'UserAuditLog', COUNT(*) FROM UserAuditLog
UNION ALL SELECT 'Devices', COUNT(*) FROM Devices
UNION ALL SELECT 'Subscriptions', COUNT(*) FROM Subscriptions
UNION ALL SELECT 'Servers', COUNT(*) FROM Servers
UNION ALL SELECT 'AccessKeys', COUNT(*) FROM AccessKeys
UNION ALL SELECT 'Sessions', COUNT(*) FROM Sessions;
GO
