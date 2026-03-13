import aiosqlite
import json
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "trading.db")

# 봇 루프 전용 영속 커넥션 (매 사이클마다 열고 닫지 않음)
_persistent_conn: aiosqlite.Connection | None = None


async def get_db():
    """요청 핸들러용 - 짧은 수명의 커넥션 반환 (호출자가 close() 책임)"""
    return await aiosqlite.connect(DB_PATH)


async def get_persistent_db() -> aiosqlite.Connection:
    """봇 루프용 - 애플리케이션 수명 내내 유지되는 커넥션 반환"""
    global _persistent_conn
    if _persistent_conn is None:
        _persistent_conn = await aiosqlite.connect(DB_PATH)
        logger.info("Persistent DB connection opened")
    return _persistent_conn


async def close_persistent_db():
    global _persistent_conn
    if _persistent_conn is not None:
        await _persistent_conn.close()
        _persistent_conn = None
        logger.info("Persistent DB connection closed")


# ─── 헬퍼 함수 ──────────────────────────────────────────────────

async def get_position(db: aiosqlite.Connection, mode: str, market: str) -> Optional[dict]:
    """특정 (mode, market) 포지션 조회. 없으면 None 반환."""
    cursor = await db.execute(
        "SELECT * FROM positions WHERE mode=? AND market=?", (mode, market)
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


async def upsert_position(db: aiosqlite.Connection, mode: str, market: str, **fields) -> None:
    """포지션 생성 또는 업데이트."""
    existing = await get_position(db, mode, market)
    if existing is None:
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" * len(fields))
        await db.execute(
            f"INSERT INTO positions (mode, market, {cols}) VALUES (?, ?, {placeholders})",
            (mode, market, *fields.values())
        )
    else:
        set_clause = ", ".join(f"{k}=?" for k in fields)
        await db.execute(
            f"UPDATE positions SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE mode=? AND market=?",
            (*fields.values(), mode, market)
        )


async def write_audit_log(
    db: aiosqlite.Connection,
    event_type: str,
    message: str,
    market: Optional[str] = None,
    mode: Optional[str] = None,
    details: Optional[dict] = None,
) -> None:
    """audit_log 테이블에 이벤트 기록."""
    details_json = json.dumps(details, ensure_ascii=False) if details else None
    await db.execute(
        "INSERT INTO audit_log (event_type, market, mode, message, details) VALUES (?, ?, ?, ?, ?)",
        (event_type, market, mode, message, details_json)
    )
    await db.commit()


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # 기존 테이블
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT NOT NULL,
                market TEXT NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                volume REAL NOT NULL,
                strategy TEXT,
                pnl REAL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_json TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 기존 paper_portfolio 유지 (폴백용)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS paper_portfolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                krw_balance REAL DEFAULT 1000000,
                btc_balance REAL DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor = await db.execute("SELECT COUNT(*) FROM paper_portfolio")
        count = (await cursor.fetchone())[0]
        if count == 0:
            await db.execute(
                "INSERT INTO paper_portfolio (krw_balance, btc_balance) VALUES (?, ?)",
                (10000000, 0)
            )

        # ── 신규 테이블 ──────────────────────────────────────────
        # 다중 마켓 포지션 (paper_portfolio 대체)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                mode          TEXT    NOT NULL DEFAULT 'paper',
                market        TEXT    NOT NULL,
                krw_balance   REAL    NOT NULL DEFAULT 0,
                asset_balance REAL    NOT NULL DEFAULT 0,
                entry_price   REAL    NOT NULL DEFAULT 0,
                position      TEXT    NOT NULL DEFAULT 'none',
                peak_price    REAL    NOT NULL DEFAULT 0,
                updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(mode, market)
            )
        """)
        # 주문 생명주기
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                market            TEXT    NOT NULL,
                mode              TEXT    NOT NULL DEFAULT 'paper',
                side              TEXT    NOT NULL,
                status            TEXT    NOT NULL DEFAULT 'created',
                price             REAL    NOT NULL DEFAULT 0,
                volume            REAL    NOT NULL DEFAULT 0,
                filled_price      REAL,
                filled_volume     REAL,
                strategy          TEXT,
                exchange_order_id TEXT,
                error_message     TEXT,
                created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 감사 로그
        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT    NOT NULL,
                market     TEXT,
                mode       TEXT,
                message    TEXT    NOT NULL,
                details    TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 인덱스
        await db.execute("CREATE INDEX IF NOT EXISTS idx_trades_market ON trades(market, mode)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_market ON orders(market, mode)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_type ON audit_log(event_type)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at)")

        await db.commit()
