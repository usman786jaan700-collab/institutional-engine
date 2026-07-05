import math, time
from collections import deque
from dataclasses import dataclass, field

def depth_weighted_imbalance(bids: dict, asks: dict, mid: float, band_pct: float) -> float:
    band = mid * (band_pct / 100)
    wb = wa = 0.0
    for price, qty in bids.items():
        dist = mid - price
        if dist > band or dist < 0:
            continue
        wb += qty * math.exp(-dist / ((band / 3) or 1e-9))
    for price, qty in asks.items():
        dist = price - mid
        if dist > band or dist < 0:
            continue
        wa += qty * math.exp(-dist / ((band / 3) or 1e-9))
    total = wb + wa
    return (wb - wa) / total if total > 0 else 0.0


class FlowSpikeDetector:
    def __init__(self, window_seconds: float, spike_mult: float):
        self.window_seconds = window_seconds
        self.spike_mult = spike_mult
        self.recent: deque[tuple[float, float]] = deque()

    def record(self, qty: float, now_ts: float):
        self.recent.append((now_ts, qty))
        cutoff = now_ts - self.window_seconds
        while self.recent and self.recent[0][0] < cutoff:
            self.recent.popleft()

    def is_spiking(self, baseline_avg_qty: float) -> bool:
        if not self.recent or baseline_avg_qty <= 0:
            return False
        rate = sum(q for _, q in self.recent) / self.window_seconds
        return rate > baseline_avg_qty * self.spike_mult


@dataclass
class CandidateWall:
    price: float
    side: str
    first_seen: float
    max_qty: float
    flow: FlowSpikeDetector
    price_moved_through: bool = False


class SmartMoneyEngine:
    """One instance per symbol. apply_depth()/apply_trade() return lists of
    event dicts: {'event': 'confirmed', ...} or {'event': 'swept', ...}."""

    def __init__(self, symbol: str, threshold_mult=6.0, persistence_seconds=4.0,
                 band_pct=0.5, flow_window=10.0, flow_spike_mult=4.0,
                 sweep_tolerance_pct=0.06):
        self.symbol = symbol
        self.threshold_mult = threshold_mult
        self.persistence_seconds = persistence_seconds
        self.band_pct = band_pct
        self.flow_window = flow_window
        self.flow_spike_mult = flow_spike_mult
        self.sweep_tolerance_pct = sweep_tolerance_pct

        self.bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}
        self.candidates: dict[tuple, CandidateWall] = {}
        self.baseline_trade_qty: deque[float] = deque(maxlen=200)
        self.active_zones: dict[tuple, dict] = {}   # key -> zone dict (side, price, ...)

    def _bucket(self, price: float, tol_pct: float = 0.06) -> float:
        step = price * (tol_pct / 100)
        return round(price / step) * step if step else price

    def apply_depth(self, bids_upd, asks_upd) -> list[dict]:
        for p, q in bids_upd:
            (self.bids.pop(p, None) if q <= 0 else self.bids.__setitem__(p, q))
        for p, q in asks_upd:
            (self.asks.pop(p, None) if q <= 0 else self.asks.__setitem__(p, q))
        if not self.bids or not self.asks:
            return []

        mid = (max(self.bids) + min(self.asks)) / 2
        imbalance = depth_weighted_imbalance(self.bids, self.asks, mid, self.band_pct)
        all_qty = list(self.bids.values()) + list(self.asks.values())
        avg = sum(all_qty) / len(all_qty)
        threshold = avg * self.threshold_mult
        now = time.time()

        for side, levels in (("bid", self.bids), ("ask", self.asks)):
            for price, qty in levels.items():
                key = (side, self._bucket(price))
                if qty <= threshold:
                    self.candidates.pop(key, None)
                    continue
                c = self.candidates.get(key)
                if c is None:
                    self.candidates[key] = CandidateWall(
                        price, side, now, qty, FlowSpikeDetector(self.flow_window, self.flow_spike_mult))
                else:
                    c.max_qty = max(c.max_qty, qty)

        events = self._evaluate_confirmations(imbalance, now)
        events += self._check_sweeps(mid)
        return events

    def apply_trade(self, price: float, qty: float) -> list[dict]:
        now = time.time()
        self.baseline_trade_qty.append(qty)
        for c in self.candidates.values():
            c.flow.record(qty, now)
            crossed = (c.side == "bid" and price < c.price) or (c.side == "ask" and price > c.price)
            if crossed:
                c.price_moved_through = True
        return self._check_sweeps(price)

    def _evaluate_confirmations(self, imbalance: float, now: float) -> list[dict]:
        events = []
        baseline_avg = (sum(self.baseline_trade_qty) / len(self.baseline_trade_qty)
                         if self.baseline_trade_qty else 0)
        for key, c in list(self.candidates.items()):
            persisted = (now - c.first_seen) >= self.persistence_seconds
            absorbed = c.flow.is_spiking(baseline_avg) and not c.price_moved_through
            if persisted and absorbed:
                factors = ["size_threshold", "persistence", "flow_absorption"]
                if (c.side == "bid" and imbalance > 0.15) or (c.side == "ask" and imbalance < -0.15):
                    factors.append("imbalance_aligned")
                zone = {
                    "event": "confirmed", "key": key, "symbol": self.symbol,
                    "side": c.side, "price": c.price, "size": round(c.max_qty, 6),
                    "confidence_factors": factors,
                }
                self.active_zones[key] = zone
                events.append(zone)
                del self.candidates[key]
        return events

    def _check_sweeps(self, price: float) -> list[dict]:
        events = []
        for key, zone in list(self.active_zones.items()):
            tol = zone["price"] * (self.sweep_tolerance_pct / 100)
            swept = (zone["side"] == "bid" and price < zone["price"] - tol) or \
                    (zone["side"] == "ask" and price > zone["price"] + tol)
            if swept:
                events.append({"event": "swept", "key": key, "symbol": self.symbol,
                                "side": zone["side"], "price": zone["price"], "swept_price": price})
                del self.active_zones[key]
        return events
