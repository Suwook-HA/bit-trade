import aiosqlite
import os
import logging

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


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS paper_portfolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                krw_balance REAL DEFAULT 1000000,
                btc_balance REAL DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Initialize paper portfolio if empty
        cursor = await db.execute("SELECT COUNT(*) FROM paper_portfolio")
        count = (await cursor.fetchone())[0]
        if count == 0:
            await db.execute(
                "INSERT INTO paper_portfolio (krw_balance, btc_balance) VALUES (?, ?)",
                (10000000, 0)
            )
        await db.commit()
