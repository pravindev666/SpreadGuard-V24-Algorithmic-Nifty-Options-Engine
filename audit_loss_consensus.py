import pandas as pd
import numpy as np

# Load the data used by the backtest
df = pd.read_csv('data/nifty_daily.csv', parse_dates=['date'])
df = df.sort_values('date')

# Indicators
# 1. EMAs
df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()

# 2. DMI (Simplified version for quick check)
# In Pine: [diplus, diminus, adx] = ta.dmi(14, 14)
def get_dmi(df):
    high = df['high']
    low = df['low']
    close = df['close']
    
    up = high.diff()
    down = -low.diff()
    
    pos_dm = np.where((up > down) & (up > 0), up, 0)
    neg_dm = np.where((down > up) & (down > 0), down, 0)
    
    tr = pd.concat([high-low, abs(high-close.shift()), abs(low-close.shift())], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    
    di_plus = 100 * pd.Series(pos_dm).rolling(14).mean() / atr
    di_minus = 100 * pd.Series(neg_dm).rolling(14).mean() / atr
    return di_plus, di_minus

df['di_plus'], df['di_minus'] = get_dmi(df)

# 3. SuperTrend (Simplified version)
def get_supertrend(df, atr_period=10, multiplier=3):
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr = pd.concat([high-low, abs(high-close.shift()), abs(low-close.shift())], axis=1).max(axis=1)
    atr = tr.rolling(atr_period).mean()
    
    hl2 = (high + low) / 2
    upperband = hl2 + (multiplier * atr)
    lowerband = hl2 - (multiplier * atr)
    
    in_uptrend = True
    supertrend = [np.nan] * len(df)
    
    for i in range(1, len(df)):
        if close.iloc[i] > upperband.iloc[i-1]:
            in_uptrend = True
        elif close.iloc[i] < lowerband.iloc[i-1]:
            in_uptrend = False
        
        if in_uptrend:
            supertrend[i] = lowerband.iloc[i]
        else:
            supertrend[i] = upperband.iloc[i]
            
    return pd.Series(supertrend), in_uptrend

st_series, _ = get_supertrend(df)
df['supertrend'] = st_series
df['st_bullish'] = df['close'] > df['supertrend']

# 4. MACD
df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
df['macd'] = df['ema12'] - df['ema26']
df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()

# Consensus Score Logic
def get_score(row):
    score = 0
    score += (1 if row['ema20'] > row['ema50'] else -1)
    score += (1 if row['di_plus'] > row['di_minus'] else -1)
    score += (1 if row['st_bullish'] else -1)
    score += (1 if row['macd'] > row['signal'] else -1)
    return score

df['consensus_score'] = df.apply(get_score, axis=1)

# Inspect loss dates
dates = ['2024-09-24', '2024-10-01']
target_dates = pd.to_datetime(dates)
results = df[df['date'].isin(target_dates)]

print(results[['date', 'close', 'ema20', 'ema50', 'di_plus', 'di_minus', 'st_bullish', 'macd', 'signal', 'consensus_score']].to_string())
