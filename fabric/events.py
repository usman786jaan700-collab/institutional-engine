from typing import TypedDict

class NormalizedTrade(TypedDict):
    symbol: str
    price: float
    qty: float
    side: str        # 'buy' or 'sell' (aggressor), derived from Binance's maker flag
    time: str

class NormalizedDepth(TypedDict):
    symbol: str
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]
    time: str
