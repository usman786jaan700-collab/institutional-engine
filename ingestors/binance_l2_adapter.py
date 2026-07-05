import asyncio, json
from datetime import datetime, timezone
import websockets
from fabric.events import NormalizedTrade, NormalizedDepth

class BinanceL2Adapter:
    WS_BASE = "wss://stream.binance.com:9443/stream?streams="

    def __init__(self, depth_levels: int = 20, depth_speed_ms: int = 100):
        self.depth_levels = depth_levels
        self.depth_speed_ms = depth_speed_ms
        self._queues = {"trade": asyncio.Queue(), "depth": asyncio.Queue()}
        self._symbols: list[str] = []
        self._started = False

    def _build_url(self) -> str:
        streams = []
        for s in self._symbols:
            low = s.lower()
            streams.append(f"{low}@aggTrade")
            streams.append(f"{low}@depth{self.depth_levels}@{self.depth_speed_ms}ms")
        return self.WS_BASE + "/".join(streams)

    async def _route(self, msg: dict):
        stream = msg.get("stream", ""); d = msg.get("data", {})
        if "@aggTrade" in stream:
            await self._queues["trade"].put(NormalizedTrade(
                symbol=d["s"], price=float(d["p"]), qty=float(d["q"]),
                side="sell" if d["m"] else "buy",
                time=datetime.fromtimestamp(d["T"] / 1000, tz=timezone.utc).isoformat(),
            ))
        elif "@depth" in stream:
            symbol = stream.split("@")[0].upper()
            await self._queues["depth"].put(NormalizedDepth(
                symbol=symbol,
                bids=[(float(p), float(q)) for p, q in d.get("bids", [])],
                asks=[(float(p), float(q)) for p, q in d.get("asks", [])],
                time=datetime.now(timezone.utc).isoformat(),
            ))

    async def _run(self):
        backoff = 1
        while True:
            try:
                async with websockets.connect(self._build_url(), ping_interval=20, ping_timeout=10) as ws:
                    backoff = 1
                    async for raw in ws:
                        await self._route(json.loads(raw))
            except (websockets.ConnectionClosed, OSError) as e:
                print(f"[binance-l2] reconnecting in {backoff}s: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _ensure_started(self, symbols):
        if self._started:
            return
        self._symbols = symbols
        self._started = True
        asyncio.create_task(self._run())

    async def stream_trades(self, symbols):
        await self._ensure_started(symbols)
        while True:
            yield await self._queues["trade"].get()

    async def stream_depth(self, symbols):
        await self._ensure_started(symbols)
        while True:
            yield await self._queues["depth"].get()
