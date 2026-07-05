import asyncio, json, os
from datetime import datetime, timezone
import asyncpg, redis.asyncio as redis
from analytics.smart_money import SmartMoneyEngine

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]

CONFIG = dict(
    threshold_mult=float(os.environ.get("THRESHOLD_MULT", "6.0")),
    persistence_seconds=float(os.environ.get("PERSISTENCE_SECONDS", "4.0")),
    band_pct=float(os.environ.get("IMBALANCE_BAND_PCT", "0.5")),
    flow_window=float(os.environ.get("FLOW_WINDOW_SECONDS", "10.0")),
    flow_spike_mult=float(os.environ.get("FLOW_SPIKE_MULT", "4.0")),
    sweep_tolerance_pct=float(os.environ.get("SWEEP_TOLERANCE_PCT", "0.06")),
)

engines: dict[str, SmartMoneyEngine] = {}
db_ids: dict[tuple, int] = {}   # (symbol, key) -> liquidity_zones.id

def engine_for(symbol: str) -> SmartMoneyEngine:
    if symbol not in engines:
        engines[symbol] = SmartMoneyEngine(symbol, **CONFIG)
    return engines[symbol]

async def get_symbol_id(pool, symbol):
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT id FROM symbols WHERE symbol=$1", symbol)

async def persist_events(pool, r, symbol, events):
    if not events:
        return
    symbol_id = await get_symbol_id(pool, symbol)
    now = datetime.now(timezone.utc)
    for ev in events:
        if ev["event"] == "confirmed":
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "INSERT INTO liquidity_zones (symbol_id, side, price, size, confidence_factors, confirmed_at) "
                    "VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
                    symbol_id, ev["side"], ev["price"], ev["size"], ev["confidence_factors"], now)
            db_ids[(symbol, ev["key"])] = row["id"]
            await r.publish(f"zones:{symbol}", json.dumps(
                {k: v for k, v in ev.items() if k != "key"}))
            print(f"[{symbol}] CONFIRMED {ev['side']} @ {ev['price']} factors={ev['confidence_factors']}")
        elif ev["event"] == "swept":
            zone_id = db_ids.pop((symbol, ev["key"]), None)
            if zone_id:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE liquidity_zones SET swept=TRUE, swept_at=$1 WHERE id=$2",
                        now, zone_id)
            await r.publish(f"sweeps:{symbol}", json.dumps(
                {k: v for k, v in ev.items() if k != "key"}))
            print(f"[{symbol}] SWEPT {ev['side']} @ {ev['price']} (price hit {ev['swept_price']})")

async def run():
    pool = await asyncpg.create_pool(DATABASE_URL)
    r = await redis.from_url(REDIS_URL)
    pubsub = r.pubsub()
    await pubsub.psubscribe("trades:*", "depth:*")
    async for msg in pubsub.listen():
        if msg["type"] != "pmessage":
            continue
        channel = msg["channel"].decode()
        data = json.loads(msg["data"])
        symbol = channel.split(":", 1)[1]
        engine = engine_for(symbol)
        if channel.startswith("depth:"):
            events = engine.apply_depth(data["bids"], data["asks"])
        else:
            events = engine.apply_trade(data["price"], data["qty"])
        await persist_events(pool, r, symbol, events)

if __name__ == "__main__":
    asyncio.run(run())
