CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE symbols (
  id SERIAL PRIMARY KEY,
  exchange TEXT NOT NULL DEFAULT 'binance',
  symbol TEXT NOT NULL UNIQUE
);

CREATE TABLE liquidity_zones (
  id BIGSERIAL PRIMARY KEY,
  symbol_id INT NOT NULL REFERENCES symbols(id),
  side TEXT NOT NULL,                 -- 'bid' | 'ask'
  price DOUBLE PRECISION NOT NULL,
  size DOUBLE PRECISION NOT NULL,
  confidence_factors TEXT[] NOT NULL,
  confirmed_at TIMESTAMPTZ NOT NULL,
  swept BOOLEAN DEFAULT FALSE,
  swept_at TIMESTAMPTZ
);
CREATE INDEX ON liquidity_zones (symbol_id, swept, confirmed_at DESC);
