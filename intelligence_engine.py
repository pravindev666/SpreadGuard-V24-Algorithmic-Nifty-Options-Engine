import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta

# --- INDICATOR HELPERS ---
def calculate_supertrend(df, period=10, multiplier=3):
    hl2 = (df['high'] + df['low']) / 2
    tr = np.maximum(df['high'] - df['low'], 
                    np.maximum((df['high'] - df['close'].shift(1)).abs(), 
                               (df['low'] - df['close'].shift(1)).abs()))
    atr_rma = tr.ewm(alpha=1/period, adjust=False).mean()
    df['upperband'] = hl2 + (multiplier * atr_rma)
    df['lowerband'] = hl2 - (multiplier * atr_rma)
    df['st_uptrend'] = True
    for i in range(1, len(df)):
        if df['close'].iloc[i] > df['upperband'].iloc[i-1]:
            df.at[df.index[i], 'st_uptrend'] = True
        elif df['close'].iloc[i] < df['lowerband'].iloc[i-1]:
            df.at[df.index[i], 'st_uptrend'] = False
        else:
            df.at[df.index[i], 'st_uptrend'] = df['st_uptrend'].iloc[i-1]
            if df['st_uptrend'].iloc[i]:
                df.at[df.index[i], 'lowerband'] = max(df['lowerband'].iloc[i], df['lowerband'].iloc[i-1])
            else:
                df.at[df.index[i], 'upperband'] = min(df['upperband'].iloc[i], df['upperband'].iloc[i-1])
    return df['st_uptrend']

def calculate_dmi(df, period=14):
    up = df['high'].diff()
    down = -df['low'].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0)
    minus_dm = np.where((down > up) & (down > 0), down, 0)
    tr = np.maximum(df['high'] - df['low'], 
                    np.maximum((df['high'] - df['close'].shift(1)).abs(), 
                               (df['low'] - df['close'].shift(1)).abs()))
    atr_rma = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * (pd.Series(plus_dm).ewm(alpha=1/period, adjust=False).mean() / atr_rma)
    minus_di = 100 * (pd.Series(minus_dm).ewm(alpha=1/period, adjust=False).mean() / atr_rma)
    return plus_di, minus_di

def adaptive_otm(base, current_atr):
    ratio = max(0.9, min(1.1, current_atr / 150.0))
    return int(round(base * ratio / 50) * 50)

def run_engine():
    print("🧠 Starting SpreadGuard Intelligence Engine [96% Backtest Mode]...")
    
    # 1. LOAD DATA
    df_d = pd.read_csv("data/nifty_daily.csv")
    df_d['date'] = pd.to_datetime(df_d['date'])
    df_d = df_d.sort_values('date')
    
    v_d = pd.read_csv("data/vix_daily.csv")
    v_d['date'] = pd.to_datetime(v_d['date'])
    v_d = v_d.sort_values('date')
    
    # 2. CORE SENSORS
    current_price = df_d['close'].iloc[-1]
    current_vix = v_d['close'].iloc[-1]
    ref_date = df_d['date'].iloc[-1]
    dow_idx = ref_date.weekday() # 0=Mon, 4=Fri
    
    # ATR & ROC
    tr = np.maximum(df_d['high'] - df_d['low'], 
                    np.maximum((df_d['high'] - df_d['close'].shift(1)).abs(), 
                               (df_d['low'] - df_d['close'].shift(1)).abs()))
    atr = tr.ewm(alpha=1/14, adjust=False).mean().iloc[-1]
    roc1 = (df_d['close'].iloc[-1] - df_d['close'].iloc[-2]) / df_d['close'].iloc[-2] * 100
    roc5 = (df_d['close'].iloc[-1] - df_d['close'].iloc[-5]) / df_d['close'].iloc[-5] * 100
    velocity = df_d['close'].pct_change(1).abs().rolling(3).sum().iloc[-1] * 100
    
    # EMA
    df_d['ema20'] = df_d['close'].ewm(span=20, adjust=False).mean()
    df_d['ema50'] = df_d['close'].ewm(span=50, adjust=False).mean()
    
    # Technical HUD Indicators
    plus_di, minus_di = calculate_dmi(df_d)
    st_uptrend = calculate_supertrend(df_d).iloc[-1]
    macd = df_d['close'].ewm(span=12, adjust=False).mean() - df_d['close'].ewm(span=26, adjust=False).mean()
    signal = macd.ewm(span=9, adjust=False).mean()
    
    # Consensus Score (0-4)
    score_4 = 0
    score_4 += (1 if (current_price > df_d['ema20'].iloc[-1]) else 0)
    score_4 += (1 if plus_di.iloc[-1] > minus_di.iloc[-1] else 0)
    score_4 += (1 if st_uptrend else 0)
    score_4 += (1 if macd.iloc[-1] > signal.iloc[-1] else 0)
    
    # 3. 96% BACKTEST DANGER SCORE (Modified 0-6 Scale)
    vix_chg_1d = (v_d['close'].iloc[-1] - v_d['close'].iloc[-2]) / v_d['close'].iloc[-2] * 100
    score_backtest = 0
    score_backtest += (1 if current_vix > 18 else 0)
    score_backtest += (1 if vix_chg_1d > 15 else 0)
    score_backtest += (1 if atr > 200 else 0)
    score_backtest += (1 if abs(roc5) > 2.0 else 0)
    
    # 4. TIER EVALUATION (The Heart of the System)
    vix_20d_avg = v_d['close'].rolling(20).mean().iloc[-1]
    vix_ceiling = min(vix_20d_avg * 1.15, 20.0)
    vix_2d_chg = (v_d['close'].iloc[-1] - v_d['close'].iloc[-3]) / v_d['close'].iloc[-3] * 100
    vix_std5 = v_d['close'].rolling(5).std().iloc[-1]
    
    dual_ok = (current_vix < vix_ceiling) and (atr < 200)
    v19_velocity_blocked = (velocity > 3.5 and score_backtest >= 1)
    
    # Bias Logic
    bull_bias = (df_d['ema20'].iloc[-1] > df_d['ema50'].iloc[-1]) and (current_price > df_d['ema50'].iloc[-1]) and (roc5 > 0.5)
    bear_bias = (df_d['ema20'].iloc[-1] < df_d['ema50'].iloc[-1]) and (current_price < df_d['ema50'].iloc[-1]) and (roc5 < -0.5)
    neut_bias = not bull_bias and not bear_bias
    
    tiers = []
    
    # --- HIGH CONVICTION ---
    tiers.append({
        "name": "VIX-Collapse", 
        "active": bool(vix_2d_chg < -15 and score_backtest < 3 and current_vix < vix_ceiling and atr < 250),
        "safe": True, "otm": 700, "type": "Bull Put"
    })
    tiers.append({
        "name": "Butterfly", 
        "active": bool(score_backtest == 0 and current_vix < 12 and atr < 150 and vix_std5 < 1.5),
        "safe": True, "otm": 200, "type": "Iron Fly"
    })
    tiers.append({
        "name": "Thursday-EXP", 
        "active": bool(dow_idx == 3 and score_backtest <= 1 and current_vix < 14 and atr < 100),
        "safe": True, "otm": adaptive_otm(600, atr), "type": "Bull Put"
    })
    tiers.append({
        "name": "Monday-RW", 
        "active": bool(not v19_velocity_blocked and dow_idx == 0 and score_backtest <= 1 and current_vix < 16 and atr <= 160 and dual_ok),
        "safe": True, "otm": adaptive_otm(680, atr), "type": "Bull Put"
    })
    
    # --- AGGRESSIVE ---
    tiers.append({
        "name": "NarrowCondor", 
        "active": bool(neut_bias and score_backtest <= 1 and atr <= 140 and current_vix <= 16),
        "safe": False, "otm": 400, "type": "Iron Condor"
    })
    tiers.append({
        "name": "Bear-Call-Offense", 
        "active": bool(bear_bias and score_backtest <= 2 and atr <= 200 and dual_ok),
        "safe": False, "otm": adaptive_otm(600, atr), "type": "Bear Call"
    })
    
    # Sniper Elite / Normal (V2024 Core)
    is_safe_regime = (score_backtest <= 2) and (current_vix < vix_ceiling)
    tiers.append({
        "name": "Sniper-Elite", 
        "active": bool(is_safe_regime and not v19_velocity_blocked and bull_bias),
        "safe": False, "otm": adaptive_otm(500, atr), "type": "Bull Put"
    })

    # 5. ANCHOR & VWAP
    anchor_signal = "NEUTRAL"
    vwap_veto = False
    try:
        df_15m = pd.read_csv("data/nifty_15m_2001_to_now.csv")
        df_15m['datetime'] = pd.to_datetime(df_15m['date'])
        df_15m.set_index('datetime', inplace=True)
        m15_latest = df_15m.iloc[-1]
        day_df = df_15m[df_15m.index.date == m15_latest.name.date()]
        if not day_df.empty:
            vwap_val = (day_df['close'] * day_df['volume']).cumsum() / day_df['volume'].cumsum()
            vwap_veto = m15_latest['close'] < vwap_val.iloc[-1]
        ema20_15m = df_15m['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ema20_1h = df_15m['close'].resample('1h').last().ffill().ewm(span=20, adjust=False).mean().iloc[-1]
        if (ema20_15m > ema20_1h) and (ema20_1h > df_d['ema20'].iloc[-1]): anchor_signal = "BULL"
        elif (ema20_15m < ema20_1h) and (ema20_1h < df_d['ema20'].iloc[-1]): anchor_signal = "BEAR"
    except Exception as e: print(f"⚠️ 15m Skipped: {e}")

    # 6. ASSEMBLE JSON
    pulse = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "spot": round(float(current_price), 2),
            "vix": round(float(current_vix), 2),
            "atr": round(float(atr), 1),
            "velocity": round(float(velocity), 2),
            "roc1": round(float(roc1), 2),
            "roc5": round(float(roc5), 2)
        },
        "intelligence": {
            "bias": "BULLISH" if bull_bias else ("BEARISH" if bear_bias else "NEUTRAL"),
            "consensus": int(score_4),
            "danger_score": int(score_backtest),
            "vix_threshold": round(float(vix_ceiling), 2),
            "vwap_veto": bool(vwap_veto),
            "anchor": anchor_signal
        },
        "tiers": tiers
    }
    
    with open("data/intelligence_pulse.json", "w") as f:
        json.dump(pulse, f, indent=4)
    print("✅ Full Intelligence Pulse [14+ Tiers] Generated!")

if __name__ == "__main__":
    run_engine()
