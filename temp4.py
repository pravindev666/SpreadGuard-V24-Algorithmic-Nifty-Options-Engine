import pandas as pd
df = pd.read_csv('backtest_v2024_results.csv', parse_dates=['Date'])
df = df[df['Date'].dt.year >= 2024].copy()

safe_tiers = ['Monday-RW', 'Wednesday-MW', 'Friday-SNP', 'Thursday-EXP', 'VIX-Collapse', 'Near-VC', 'Butterfly']
yellow_df = df[~df['Tier'].isin(safe_tiers)].copy()

total_yellow = len(yellow_df)
wins = len(yellow_df[yellow_df['PnL'] > 0])
losses = len(yellow_df[yellow_df['PnL'] <= 0])

print(f"Total Yellow Trades (2024-2026): {total_yellow}")
print(f"Wins: {wins}")
print(f"Losses: {losses}")
