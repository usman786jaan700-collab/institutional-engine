import asyncio, json, os
from datetime import datetime
import asyncpg, redis.asyncio as redis
from ingestors.binance_l2_adapter import BinanceL2Adapter

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
SYMBOLS = os.environ["SYMBOLS"].split(",")
DEPTH_LEVELS = int(os.environ.get("DEPTH_LEVELS", "20"))
DEPTH_SPEED_MS = int(os.environ.get("DEPTH_SPEED_MS", "100"))

async def ensure_symbol(pool, symbol):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO symbols (exchange, symbol) VALUES ('binance', $1) "
            "ON CONFLICT (symbol) DO UPDATE SET symbol=EXCLUDED.symbol RETURNING id",
            symbol)
        return row["id"]

async def consume_trades(r, adapter):
    async for t in adapter.stream_trades(SYMBOLS):
        await r.publish(f"trades:{t['symbol']}", json.dumps(t))

async def consume_depth(r, adapter):
    async for d in adapter.stream_depth(SYMBOLS):
        await r.publish(f"depth:{d['symbol']}", json.dumps(d))

async def run():
    pool = await asyncpg.create_pool(DATABASE_URL)
    r = await redis.from_url(REDIS_URL)
    for s in SYMBOLS:
        await ensure_symbol(pool, s)
    adapter = BinanceL2Adapter(DEPTH_LEVELS, DEPTH_SPEED_MS)
    await asyncio.gather(
        consume_trades(r, adapter),
        consume_depth(r, adapter),
    )

if __name__ == "__main__":
    asyncio.run(run())
