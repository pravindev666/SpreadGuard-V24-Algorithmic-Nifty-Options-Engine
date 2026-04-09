import pandas as pd
import numpy as np
import json
import os
from datetime import datetime

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

def run_engine():
    print("🧠 Starting Pure Deep Awareness Engine...")
    
    # 1. LOAD DATA
    df_d = pd.read_csv("data/nifty_daily.csv")
    v_d = pd.read_csv("data/vix_daily.csv")
    df_d['date'] = pd.to_datetime(df_d['date'])
    v_d['date'] = pd.to_datetime(v_d['date'])
    
    # 2. CORE SENSORS (DAILY)
    current_price = df_d['close'].iloc[-1]
    current_vix = v_d['close'].iloc[-1]
    dow_idx = df_d['date'].iloc[-1].weekday()
    
    tr = np.maximum(df_d['high'] - df_d['low'], 
                    np.maximum((df_d['high'] - df_d['close'].shift(1)).abs(), 
                               (df_d['low'] - df_d['close'].shift(1)).abs()))
    current_atr = tr.ewm(alpha=1/14, adjust=False).mean().iloc[-1]
    
    df_d['abs_ret'] = df_d['close'].pct_change().abs() * 100
    velocity = df_d['abs_ret'].rolling(3).sum().iloc[-1]
    
    roc1 = (df_d['close'].iloc[-1] - df_d['close'].iloc[-2]) / df_d['close'].iloc[-2] * 100
    roc5 = (df_d['close'].iloc[-1] - df_d['close'].iloc[-5]) / df_d['close'].iloc[-5] * 100
    
    # Technical Pulse (Replicating Pine HUD)
    plus_di, minus_di = calculate_dmi(df_d)
    st_uptrend = calculate_supertrend(df_d).iloc[-1]
    df_d['ema20'] = df_d['close'].ewm(span=20, adjust=False).mean()
    df_d['ema50'] = df_d['close'].ewm(span=50, adjust=False).mean()
    
    ema_label = "BULL" if current_price > df_d['ema20'].iloc[-1] > df_d['ema50'].iloc[-1] else ("BEAR" if current_price < df_d['ema20'].iloc[-1] < df_d['ema50'].iloc[-1] else "NEUTRAL")
    dmi_label = "BULL" if plus_di.iloc[-1] > minus_di.iloc[-1] else "BEAR"
    st_label = "BULL" if st_uptrend else "BEAR"
    macd = df_d['close'].ewm(span=12, adjust=False).mean() - df_d['close'].ewm(span=26, adjust=False).mean()
    sig = macd.ewm(span=9, adjust=False).mean()
    macd_label = "BULL" if macd.iloc[-1] > sig.iloc[-1] else "BEAR"

    score_4 = (1 if ema_label == "BULL" else 0) + (1 if dmi_label == "BULL" else 0) + (1 if st_label == "BULL" else 0) + (1 if macd_label == "BULL" else 0)
    
    # 3. Decision Engine (96% Rules)
    vix_chg_1d = (v_d['close'].iloc[-1] - v_d['close'].iloc[-2]) / v_d['close'].iloc[-2] * 100
    danger_score = 0
    if current_vix > 18: danger_score += 1
    if vix_chg_1d > 15: danger_score += 1
    if current_atr > 200: danger_score += 1
    if abs(roc5) > 2.0: danger_score += 1
    
    vix_20d_avg = v_d['close'].rolling(20).mean().iloc[-1]
    vix_ceiling = min(vix_20d_avg * 1.15, 22.0)
    vix_2d_chg = (v_d['close'].iloc[-1] - v_d['close'].iloc[-3]) / v_d['close'].iloc[-3] * 100
    
    # VIX Divergence Logic
    vix_roc5 = (v_d['close'].iloc[-1] - v_d['close'].iloc[-5]) / v_d['close'].iloc[-5]
    vix_div = "DIVERGENT (🚨)" if (vix_roc5 > 0 and roc5 > 0) else "STABLE"

    # MODE & STATUS Logic
    mode_label = "NORMAL"
    if danger_score >= 3 or current_vix > 22: mode_label = "LOCKDOWN"
    elif danger_score >= 2: mode_label = "CAUTION"
    
    status_label = "STABLE"
    if velocity > 5.4 or vix_chg_1d > 12: status_label = "⚡ STORM"
    elif velocity > 4.0: status_label = "ACTIVE"
    
    # 4. TIER EVALUATION
    tiers = []
    bull_bias = (ema_label == "BULL")
    bear_bias = (ema_label == "BEAR")
    neut_bias = not bull_bias and not bear_bias
    
    tiers.append({"name": "VIX-Collapse", "active": bool(vix_2d_chg < -15 and danger_score < 3), "safe": True, "otm": 700, "type": "Bull Put"})
    tiers.append({"name": "Near-VC", "active": bool(-15 <= vix_2d_chg < -10 and danger_score < 3), "safe": True, "otm": 700, "type": "Bull Put"})
    tiers.append({"name": "Butterfly", "active": bool(danger_score == 0 and current_vix < 12 and current_atr < 150), "safe": True, "otm": 200, "type": "Iron Fly"})
    tiers.append({"name": "Thursday-EXP", "active": bool(dow_idx == 3 and danger_score <= 1), "safe": True, "otm": 600, "type": "Bull Put"})
    tiers.append({"name": "Monday-RW", "active": bool(dow_idx == 0 and danger_score <= 1), "safe": True, "otm": 680, "type": "Bull Put"})
    tiers.append({"name": "NarrowCondor", "active": bool(neut_bias and danger_score <= 1), "safe": False, "otm": 400, "type": "Iron Condor"})
    tiers.append({"name": "Bear-Call", "active": bool(bear_bias and danger_score <= 2), "safe": False, "otm": 600, "type": "Bear Call"})
    tiers.append({"name": "HighATR-Cautious", "active": bool(current_atr > 220 and danger_score <= 2), "safe": False, "otm": 800, "type": "Bull Put"})

    # 5. ANCHOR & MTF
    anchor_label = "NEUTRAL"
    mtf_label = "CONFLICT"
    try:
        df_15m = pd.read_csv("data/nifty_15m_2001_to_now.csv")
        df_15m['datetime'] = pd.to_datetime(df_15m['date'])
        df_15m.set_index('datetime', inplace=True)
        ema20_15m = df_15m['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ema20_1h = df_15m['close'].resample('1h').last().ffill().ewm(span=20, adjust=False).mean().iloc[-1]
        if (ema20_15m > ema20_1h) and (ema20_1h > df_d['ema20'].iloc[-1]): 
            anchor_label = "80% Strategy"; mtf_label = "STACKED-UP"
        elif (ema20_15m < ema20_1h) and (ema20_1h < df_d['ema20'].iloc[-1]): 
            anchor_label = "20% Strategy"; mtf_label = "STACKED-DOWN"
    except: pass

    pulse = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "spot": round(float(current_price), 2),
            "vix": round(float(current_vix), 2),
            "atr": round(float(current_atr), 1),
            "velocity": round(float(velocity), 2),
            "vix_div": vix_div
        },
        "intelligence": {
            "mode": mode_label,
            "status": status_label,
            "danger_score": int(danger_score),
            "vix_threshold": round(float(vix_ceiling), 2),
            "consensus": f"+{score_4}/4 Match",
            "anchor": anchor_label,
            "mtf": mtf_label,
            "sensors": {
                "ema": ema_label,
                "dmi": dmi_label,
                "st": st_label,
                "macd": macd_label
            }
        },
        "tiers": tiers
    }
    
    with open("data/intelligence_pulse.json", "w") as f:
        json.dump(pulse, f, indent=4)
    print("✅ Deep Awareness Pulse Generated!")

if __name__ == "__main__":
    run_engine()
