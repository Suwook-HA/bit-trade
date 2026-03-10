import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "trading.db")


async def get_db():
    return await aiosqlite.connect(DB_PATH)


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
