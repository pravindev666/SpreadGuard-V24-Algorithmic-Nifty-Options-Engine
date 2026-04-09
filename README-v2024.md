# SpreadGuard V2024: Algorithmic Nifty Options Engine

A purely mechanical, zero-prediction options engine for Nifty 50. Utilizing a dual-tier framework, it synthesizes 15-minute intraday tick data to dynamically calculate volatility and ATR to systematically sell deep out-of-the-money credit spreads. Engineered for maximum capital protection.

## 🚀 Recent Architecture Updates (V2024)

### 1. Data Pipeline Overhaul (Pseudo-Live Ticking)
- **Live Candle Synthesis:** Script `data_updater.py` now downloads 15-minute Nifty Spot / VIX blocks and dynamically aggregates them into active daily candles intraday. This allows the system to read "EOD" metrics while the market is still open.
- **Continuous Auto-Feed:** Added `live_feed.bat` background task to endlessly loop data extraction during market hours.

### 2. HUD & Dashboard Upgrade
- Rebuilt Streamlit UI into an "All-Tiers Radar."
- Implemented native `st.rerun()` looping so the dashboard inherently pulses and updates dynamically every 30 seconds without user refreshing.
- Visually split tiers into **🟢 High Conviction (Safe)** vs **🟡 Aggressive (High Frequency)**.
- Directly calculates exact strike prices (e.g., Sell 23000 PE) rather than just stating raw OTM distances.

### 4. Elite Intelligence & Forensic Audit (New)
- **Trend Cluster Consensus**: Hardened scoring engine (EMA, DMI, SuperTrend, MACD). Implemented **Momentum Shock Veto** to auto-defuse during 1%+ directional crashes.
- **Anchor Strategy (80% Conviction)**: Integrated Multi-Timeframe (15m/1h/Daily) EMA alignment and **VWAP Veto** sensors to identify institutional demand zones.
- **VIX Divergence Sensor**: Real-time monitoring of Price-vs-Fear divergence to detect "Hidden Crashes" (e.g., Sept 2024 Case).
- **Forensic Audit (Jan 2024 - Present)**:
    - **Original V2024**: ~98% Win Rate.
    - **Intelligence Filtered**: Successfully **AUTO-SKIPPED** the Oct 1, 2024 breach. Identified Sept 24, 2024 as irreducible "Tail Risk" (Technical Mirage).

## ⚙️ Disclaimer
This system leverages extremely structured deep-OTM selling. While win-rates historically exceed 95%, black-swan tail-risk is inherent in algorithmic spread trading. Use stop-loss protocols or mechanical fire doors if holding across chaotic macro-regimes.
