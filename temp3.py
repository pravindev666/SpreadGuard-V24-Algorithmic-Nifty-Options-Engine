import pandas as pd
df = pd.read_csv('backtest_v2024_results.csv', parse_dates=['Date'])
df['Year'] = df['Date'].dt.year
df = df[df['Year'] >= 2024].copy()

safe_tiers = ['Monday-RW', 'Wednesday-MW', 'Friday-SNP', 'Thursday-EXP', 'VIX-Collapse', 'Near-VC', 'Butterfly']
df['Category'] = df['Tier'].apply(lambda x: 'Green' if x in safe_tiers else 'Yellow')
df['MonthStr'] = df['Date'].dt.strftime('%b %Y')

crosstab = pd.crosstab(df['MonthStr'], df['Category'])
crosstab.index = pd.to_datetime(crosstab.index, format='%b %Y')
crosstab = crosstab.sort_index()
crosstab.index = crosstab.index.strftime('%b %Y')
print(crosstab.to_string())
