from fastapi import FastAPI
import asyncpg, os

app = FastAPI(title="Smart Money Engine API")
DATABASE_URL = os.environ["DATABASE_URL"]

@app.on_event("startup")
async def startup():
    app.state.pool = await asyncpg.create_pool(DATABASE_URL)

@app.get("/zones/{symbol}")
async def get_zones(symbol: str, active_only: bool = True):
    q = ("SELECT z.* FROM liquidity_zones z JOIN symbols s ON s.id=z.symbol_id "
         "WHERE s.symbol=$1 " + ("AND z.swept=FALSE " if active_only else "") +
         "ORDER BY z.confirmed_at DESC LIMIT 200")
    async with app.state.pool.acquire() as conn:
        rows = await conn.fetch(q, symbol)
    return [dict(r) for r in rows]

@app.get("/zones/{symbol}/outcomes")
async def zone_outcomes(symbol: str):
    async with app.state.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT z.side, z.swept, COUNT(*) as n, AVG(z.size) as avg_size "
            "FROM liquidity_zones z JOIN symbols s ON s.id=z.symbol_id "
            "WHERE s.symbol=$1 GROUP BY z.side, z.swept", symbol)
    return [dict(r) for r in rows]
