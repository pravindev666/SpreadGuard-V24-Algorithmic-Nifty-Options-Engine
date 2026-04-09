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
    print("🧠 Starting SpreadGuard Intelligence Engine...")
    
    # 1. LOAD DATA
    df_d = pd.read_csv("data/nifty_daily.csv")
    df_d['date'] = pd.to_datetime(df_d['date'])
    df_d = df_d.sort_values('date')
    
    v_d = pd.read_csv("data/vix_daily.csv")
    v_d['date'] = pd.to_datetime(v_d['date'])
    v_d = v_d.sort_values('date')
    
    # 2. CORE SENSORS (VARS)
    current_price = df_d['close'].iloc[-1]
    current_vix = v_d['close'].iloc[-1]
    
    # 3. CONVENIENCE CALCS
    df_d['ema20'] = df_d['close'].ewm(span=20, adjust=False).mean()
    df_d['ema50'] = df_d['close'].ewm(span=50, adjust=False).mean()
    plus_di, minus_di = calculate_dmi(df_d)
    df_d['st_uptrend'] = calculate_supertrend(df_d)
    macd = df_d['close'].ewm(span=12, adjust=False).mean() - df_d['close'].ewm(span=26, adjust=False).mean()
    signal = macd.ewm(span=9, adjust=False).mean()
    
    # 0-4 Consensus (Matches Pine Script HUD Visibility)
    score_4 = 0
    # 1. EMA
    is_ema_bull = (df_d['ema20'].iloc[-1] > df_d['ema50'].iloc[-1]) and (current_price > df_d['ema20'].iloc[-1])
    score_4 += (1 if is_ema_bull else 0)
    # 2. DMI
    score_4 += (1 if plus_di.iloc[-1] > minus_di.iloc[-1] else 0)
    # 3. SuperTrend
    score_4 += (1 if df_d['st_uptrend'].iloc[-1] else 0)
    # 4. MACD
    score_4 += (1 if macd.iloc[-1] > signal.iloc[-1] else 0)
    
    bias = "CONSOLIDATING"
    if score_4 >= 3: bias = "BULLISH BIAS"
    elif score_4 == 0: bias = "BEARISH BIAS"
    elif score_4 == 1: bias = "NEUTRAL (Bearish)"
    elif score_4 == 2: bias = "NEUTRAL (Bullish)"

    # Momentum Shock
    roc1 = (df_d['close'].iloc[-1] - df_d['close'].iloc[-2]) / df_d['close'].iloc[-2] * 100
    shock = (roc1 < -1.0) and (df_d['close'].iloc[-1] < df_d['open'].iloc[-1])
    
    # 4. ANCHOR & VWAP (Requires 15m)
    anchor_signal = "NEUTRAL"
    vwap_veto = False
    is_vix_div = False
    
    try:
        df_15m = pd.read_csv("data/nifty_15m_2001_to_now.csv")
        df_15m['datetime'] = pd.to_datetime(df_15m['date'])
        df_15m.set_index('datetime', inplace=True)
        
        # Latest Snap
        m15_latest = df_15m.iloc[-1]
        
        # VWAP Logic matches Pine
        day_df = df_15m[df_15m.index.date == m15_latest.name.date()]
        if not day_df.empty:
            vwap_val = (day_df['close'] * day_df['volume']).cumsum() / day_df['volume'].cumsum()
            vwap_veto = m15_latest['close'] < vwap_val.iloc[-1]
        
        # MTF
        ema20_15m = df_15m['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ema20_1h = df_15m['close'].resample('1h').last().ffill().ewm(span=20, adjust=False).mean().iloc[-1]
        
        if (ema20_15m > ema20_1h) and (ema20_1h > df_d['ema20'].iloc[-1]): anchor_signal = "BULL"
        elif (ema20_15m < ema20_1h) and (ema20_1h < df_d['ema20'].iloc[-1]): anchor_signal = "BEAR"
        
        # VIX Div (5d)
        vix_roc5 = (v_d['close'].iloc[-1] - v_d['close'].iloc[-5]) / v_d['close'].iloc[-5]
        price_roc5 = (df_d['close'].iloc[-1] - df_d['close'].iloc[-5]) / df_d['close'].iloc[-5]
        is_vix_div = (vix_roc5 > 0) and (price_roc5 > 0)
    except Exception as e:
        print(f"⚠️ 15m Insight Skipped: {e}")

    # 5. OTM LADDER
    tr = np.maximum(df_d['high'] - df_d['low'], 
                    np.maximum((df_d['high'] - df_d['close'].shift(1)).abs(), 
                               (df_d['low'] - df_d['close'].shift(1)).abs()))
    atr = tr.ewm(alpha=1/14, adjust=False).mean().iloc[-1]
    
    # 6. ASSEMBLE PULSE
    pulse = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": {
            "spot": round(float(current_price), 2),
            "vix": round(float(current_vix), 2),
            "atr": round(float(atr), 1),
            "velocity": round(float(abs(roc1)), 2),
            "roc1": round(float(roc1), 2),
            "roc5": round(float(price_roc5 * 100), 2) if 'price_roc5' in locals() else 0
        },
        "intelligence": {
            "bias": bias,
            "score": int(score_4),
            "shock": bool(shock),
            "anchor": anchor_signal,
            "vwap_veto": bool(vwap_veto),
            "vix_div": bool(is_vix_div)
        },
        "strikes": {
            "bp_500": int(round((current_price - 500) / 50) * 50),
            "bc_500": int(round((current_price + 500) / 50) * 50),
            "bp_700": int(round((current_price - 700) / 50) * 50),
            "bc_700": int(round((current_price + 700) / 50) * 50)
        }
    }
    
    # 7. SAVE OUTPUT
    os.makedirs("data", exist_ok=True)
    with open("data/intelligence_pulse.json", "w") as f:
        json.dump(pulse, f, indent=4)
    
    print("✅ Intelligence Pulse Generated!")

if __name__ == "__main__":
    run_engine()
