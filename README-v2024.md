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

### 3. Backtest Engine Corrections
- **Decay Physics Repaired:** Hardened `simulate_trade` to accurately respect physical options time-decay requirements before hitting Take-Profit multipliers, eliminating false Day-1 closures.
- **Structural Bull Bias:** Mapped default tier logic to heavily favor Bull Put spreads due to India VIX premium skew and Nifty's macro upward trajectory. 

## ⚙️ Disclaimer
This system leverages extremely structured deep-OTM selling. While win-rates historically exceed 95%, black-swan tail-risk is inherent in algorithmic spread trading. Use stop-loss protocols or mechanical fire doors if holding across chaotic macro-regimes.
