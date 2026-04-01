-- ============================================================
-- Asystent Giełdowy - Pełny setup Supabase
-- Użytkownicy zarządzani przez Supabase Auth (auth.users)
-- Tu trzymamy tylko dodatkowe dane profilu
-- Wklej CAŁOŚĆ do SQL Editor i kliknij Run
-- ============================================================

-- PROFILE (dodatkowe dane usera - auth.users obsługuje email/hasło)
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    risk_profile TEXT DEFAULT 'medium' CHECK (risk_profile IN ('low', 'medium', 'high')),
    budget_pln DECIMAL(12,2) DEFAULT 0,
    preferred_currency TEXT DEFAULT 'PLN',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Trigger: automatycznie tworzy profil gdy użytkownik się rejestruje
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id)
  VALUES (NEW.id)
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- PORTFELE
CREATE TABLE IF NOT EXISTS portfolios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT DEFAULT 'Mój portfel',
    broker TEXT DEFAULT 'manual',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- POZYCJE W PORTFELU
CREATE TABLE IF NOT EXISTS portfolio_positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id UUID REFERENCES portfolios(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    asset_type TEXT NOT NULL DEFAULT 'crypto' CHECK (asset_type IN ('crypto', 'stock', 'etf')),
    quantity DECIMAL(18,8) NOT NULL,
    avg_buy_price DECIMAL(12,4) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'PLN',
    bought_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- SNAPSHOTS RYNKOWE (co 1h)
CREATE TABLE IF NOT EXISTS market_snapshots (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    price_pln DECIMAL(12,4),
    price_usd DECIMAL(12,4),
    price_change_24h DECIMAL(8,4),
    volume_24h DECIMAL(20,2),
    market_cap DECIMAL(20,2),
    rsi_14 DECIMAL(6,2),
    macd_signal TEXT,
    fear_greed_index INTEGER,
    snapshot_at TIMESTAMPTZ DEFAULT NOW()
);

-- ZDARZENIA (triggery: tweet, news)
CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL CHECK (source IN ('twitter', 'news', 'macro')),
    source_id TEXT,
    author TEXT,
    content TEXT NOT NULL,
    url TEXT,
    relevance_score DECIMAL(4,2) DEFAULT 0,
    affected_assets TEXT[] DEFAULT '{}',
    detected_at TIMESTAMPTZ DEFAULT NOW()
);

-- PREDYKCJE
CREATE TABLE IF NOT EXISTS predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID REFERENCES events(id) ON DELETE SET NULL,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    symbol TEXT,
    scenarios JSONB NOT NULL DEFAULT '[]',
    recommendation JSONB NOT NULL DEFAULT '{}',
    llm_reasoning TEXT,
    confidence TEXT DEFAULT 'medium' CHECK (confidence IN ('low', 'medium', 'high')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    verified_at TIMESTAMPTZ,
    actual_outcome TEXT,
    accuracy_score DECIMAL(4,2)
);

-- HISTORIA CHATU
CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    session_id UUID NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    context JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ALERTY
CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    event_id UUID REFERENCES events(id) ON DELETE SET NULL,
    prediction_id UUID REFERENCES predictions(id) ON DELETE SET NULL,
    type TEXT NOT NULL CHECK (type IN ('event_trigger', 'price_alert', 'rsi_signal', 'news')),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    priority TEXT DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- USTAWIENIA ALERTÓW
CREATE TABLE IF NOT EXISTS alert_settings (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    twitter_trigger BOOLEAN DEFAULT TRUE,
    news_trigger BOOLEAN DEFAULT TRUE,
    rsi_alert BOOLEAN DEFAULT TRUE,
    rsi_threshold_oversold INTEGER DEFAULT 30,
    rsi_threshold_overbought INTEGER DEFAULT 70,
    price_change_alert BOOLEAN DEFAULT TRUE,
    price_change_threshold DECIMAL(5,2) DEFAULT 5.0,
    monitored_symbols TEXT[] DEFAULT ARRAY['BTC','ETH']
);

-- INDEKSY
CREATE INDEX IF NOT EXISTS idx_market_snapshots_symbol_time ON market_snapshots(symbol, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_detected ON events(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_source_id ON events(source, source_id);
CREATE INDEX IF NOT EXISTS idx_predictions_user ON predictions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_user_unread ON alerts(user_id, is_read, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_portfolio_positions_portfolio ON portfolio_positions(portfolio_id);

-- WYŁĄCZ RLS na tabelach publicznych (używamy service_role key)
ALTER TABLE profiles DISABLE ROW LEVEL SECURITY;
ALTER TABLE portfolios DISABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_positions DISABLE ROW LEVEL SECURITY;
ALTER TABLE market_snapshots DISABLE ROW LEVEL SECURITY;
ALTER TABLE events DISABLE ROW LEVEL SECURITY;
ALTER TABLE predictions DISABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages DISABLE ROW LEVEL SECURITY;
ALTER TABLE alerts DISABLE ROW LEVEL SECURITY;
ALTER TABLE alert_settings DISABLE ROW LEVEL SECURITY;
