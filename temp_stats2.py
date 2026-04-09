import pandas as pd
df = pd.read_csv('backtest_v2024_results.csv', parse_dates=['Date'])
df = df[df['Date'].dt.year >= 2024].copy()

safe_tiers = ['Monday-RW', 'Wednesday-MW', 'Friday-SNP', 'Thursday-EXP', 'VIX-Collapse', 'Near-VC', 'Butterfly']

df['Category'] = df['Tier'].apply(lambda x: '🟢 Green (Safe)' if x in safe_tiers else '🟡 Yellow (Aggressive)')
df['Month'] = df['Date'].dt.strftime('%Y - %m')

crosstab = pd.crosstab(df['Month'], df['Category'], fill_value=0)
crosstab['Total'] = crosstab.sum(axis=1)

print('Month-wise Trade Frequency (2024 - 2026):')
print('-' * 60)
print(crosstab.to_string())
print('-' * 60)
print('Total Trades Since Jan 2024:')
print(crosstab.sum(numeric_only=True).to_string())
