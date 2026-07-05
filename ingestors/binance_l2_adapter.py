import asyncio, json
from datetime import datetime, timezone
import websockets
from fabric.events import NormalizedTrade, NormalizedDepth

class BinanceL2Adapter:
    WS_BASE = "wss://stream.binance.com:9443/stream?streams="

    def __init__(self, depth_levels: int = 20, depth_speed_ms: int = 100):
        self.depth_levels = depth_levels
        self.depth_speed_ms = depth_speed_ms
        self._queues = {"trade": asyncio.Queue(), "depth": as
