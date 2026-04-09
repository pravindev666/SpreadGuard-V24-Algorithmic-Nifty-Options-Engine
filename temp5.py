import pandas as pd
df = pd.read_csv('backtest_v2024_results.csv', parse_dates=['Date'])
df = df[df['Date'].dt.year >= 2024].copy()

safe_tiers = ['Monday-RW', 'Wednesday-MW', 'Friday-SNP', 'Thursday-EXP', 'VIX-Collapse', 'Near-VC', 'Butterfly']
yellow_df = df[~df['Tier'].isin(safe_tiers)].copy()

losses_df = yellow_df[yellow_df['PnL'] <= 0]
print(losses_df[['Date', 'Tier', 'Side', 'HoldDays', 'PnL']].to_string())
