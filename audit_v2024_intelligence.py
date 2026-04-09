import pandas as pd
import numpy as np
import os

def calculate_supertrend(df, period=10, multiplier=3):
    hl2 = (df['high'] + df['low']) / 2
    df['tr'] = np.maximum(df['high'] - df['low'], 
                          np.maximum((df['high'] - df['close'].shift(1)).abs(), 
                                     (df['low'] - df['close'].shift(1)).abs()))
    df['atr_rma'] = df['tr'].ewm(alpha=1/period, adjust=False).mean()
    df['upperband'] = hl2 + (multiplier * df['atr_rma'])
    df['lowerband'] = hl2 - (multiplier * df['atr_rma'])
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
    df['up'] = df['high'].diff()
    df['down'] = -df['low'].diff()
    df['plus_dm'] = np.where((df['up'] > df['down']) & (df['up'] > 0), df['up'], 0)
    df['minus_dm'] = np.where((df['down'] > df['up']) & (df['down'] > 0), df['down'], 0)
    tr = np.maximum(df['high'] - df['low'], 
                    np.maximum((df['high'] - df['close'].shift(1)).abs(), 
                               (df['low'] - df['close'].shift(1)).abs()))
    atr_rma = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * (pd.Series(df['plus_dm']).ewm(alpha=1/period, adjust=False).mean() / atr_rma)
    minus_di = 100 * (pd.Series(df['minus_dm']).ewm(alpha=1/period, adjust=False).mean() / atr_rma)
    return plus_di, minus_di

def run_audit():
    print("🚀 Running Final Corrected Intelligence Audit (Col: Side Fix)...")
    df = pd.read_csv("data/nifty_daily.csv")
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['plus_di'], df['minus_di'] = calculate_dmi(df)
    df['st_uptrend'] = calculate_supertrend(df)
    df['macd'] = df['close'].ewm(span=12, adjust=False).mean() - df['close'].ewm(span=26, adjust=False).mean()
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['roc1'] = df['close'].pct_change() * 100
    df['score'] = 0
    df.loc[(df['ema20'] > df['ema50']) & (df['close'] > df['ema20']), 'score'] += 1
    df.loc[(df['ema20'] < df['ema50']) & (df['close'] < df['ema20']), 'score'] -= 1
    df.loc[df['plus_di'] > df['minus_di'], 'score'] += 1
    df.loc[df['plus_di'] < df['minus_di'], 'score'] -= 1
    df.loc[df['st_uptrend'], 'score'] += 1
    df.loc[df['st_uptrend'] == False, 'score'] -= 1
    df.loc[df['macd'] > df['signal'], 'score'] += 1
    df.loc[df['macd'] < df['signal'], 'score'] -= 1
    df.loc[(df['close'] < df['open']) & (df['roc1'] < -1.0), 'score'] -= 2
    df['bias'] = 'NEUTRAL'
    df.loc[df['score'] >= 3, 'bias'] = 'STRONG BULL'
    df.loc[df['score'] == 2, 'bias'] = 'BULL BIAS'
    df.loc[df['score'] <= -3, 'bias'] = 'STRONG BEAR'
    df.loc[df['score'] == -2, 'bias'] = 'BEAR BIAS'

    df_15m = pd.read_csv("data/nifty_15m_2001_to_now.csv")
    df_15m['datetime'] = pd.to_datetime(df_15m['date'])
    df_15m.set_index('datetime', inplace=True)
    df_15m['date_only'] = df_15m.index.date
    session_opens = df_15m.groupby('date_only')['open'].first().to_dict()
    df_15m['ema20_15m'] = df_15m['close'].ewm(span=20, adjust=False).mean()
    df_1h = df_15m.resample('1h').last().dropna()
    df_1h['ema20_1h'] = df_1h['close'].ewm(span=20, adjust=False).mean()
    
    res = pd.read_csv("backtest_v2024_results.csv")
    res['Date'] = pd.to_datetime(res['Date'])
    audit = pd.merge(res, df[['date', 'score', 'bias', 'close', 'ema20']], left_on='Date', right_on='date', how='left')
    audit['Anchor_Signal'] = 'NEUTRAL'
    audit['VWAP_Veto'] = False
    for idx, row in audit.iterrows():
        t_date = row['Date']
        snap = t_date.replace(hour=11, minute=30)
        try:
            m15 = df_15m.iloc[df_15m.index.get_indexer([snap], method='nearest')[0]]
            h1 = df_1h.iloc[df_1h.index.get_indexer([snap], method='nearest')[0]]
            if (m15['ema20_15m'] > h1['ema20_1h']) and (h1['ema20_1h'] > row['ema20']): audit.at[idx, 'Anchor_Signal'] = 'BULL'
            elif (m15['ema20_15m'] < h1['ema20_1h']) and (h1['ema20_1h'] < row['ema20']): audit.at[idx, 'Anchor_Signal'] = 'BEAR'
            if m15['close'] < session_opens.get(t_date.date()): audit.at[idx, 'VWAP_Veto'] = True
        except: pass

    # ELITE ACTION PLAN (Fixed for Backtest Labels)
    audit['Action'] = 'TRADE'
    bullish_sides = ['Bull Put', 'Butterfly', 'Condor']
    
    # Apply Vetoes
    audit.loc[(audit['Side'].isin(bullish_sides)) & (audit['bias'] == 'NEUTRAL'), 'Action'] = 'SKIP (BIAS)'
    audit.loc[(audit['Side'].isin(bullish_sides)) & (audit['bias'].str.contains('BEAR')), 'Action'] = 'SKIP (BIAS)'
    audit.loc[(audit['Side'].isin(bullish_sides)) & (audit['Anchor_Signal'] != 'BULL'), 'Action'] = 'SKIP (ANCHOR)'
    audit.loc[(audit['Side'].isin(bullish_sides)) & (audit['VWAP_Veto'] == True), 'Action'] = 'SKIP (VWAP VETO)'
    
    # Calculate P&L
    audit['Filtered_PnL'] = np.where(audit['Action'] == 'TRADE', audit['PnL'], 0)
    
    # Summary
    print("\n" + "="*55)
    print("📊 FINAL INTELLIGENCE AUDIT (V2024 ELITE)")
    print("="*55)
    print(f"Total Trades: {len(audit)}")
    print(f"Skipped:      {len(audit[audit['Action'] != 'TRADE'])}")
    print(f"Executed:     {len(audit[audit['Action'] == 'TRADE'])}")
    
    orig_p = audit['PnL'].sum()
    filt_p = audit['Filtered_PnL'].sum()
    print(f"\nOriginal Profit: ₹{orig_p:,.0f}")
    print(f"Filtered Profit: ₹{filt_p:,.0f}")
    print(f"Profit Gain:     ₹{filt_p - orig_p:,.0f}")
    
    print("\n🔍 LOSS PREVENTION CHECK (SEPT/OCT 2024):")
    for d_str in ['2024-09-24', '2024-10-01']:
        m = audit[audit['Date'] == pd.to_datetime(d_str)]
        if not m.empty:
            for _, r in m.iterrows():
                print(f"Date: {d_str} | Bias: {r['bias']} | Anchor: {r['Anchor_Signal']} | VWAP Veto: {r['VWAP_Veto']} | Action: {r['Action']} | Result: {'SAVED!' if r['Action'] != 'TRADE' else 'LOST'}")
                
    audit.to_csv("audit_v2024_elite_final.csv", index=False)

if __name__ == "__main__":
    run_audit()
