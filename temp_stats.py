import pandas as pd

try:
    df = pd.read_csv('strike_breach_audit.csv')
    df['Date'] = pd.to_datetime(df['Date'])
    df = df[df['Date'].dt.year >= 2024].copy()

    safe_tiers = ['Monday-RW', 'Wednesday-MW', 'Friday-SNP', 'Thursday-EXP', 'VIX-Collapse', 'Near-VC', 'Butterfly']

    df['Category'] = df['Tier'].apply(lambda x: 'Safe' if x in safe_tiers else 'Unsafe')
    df['Month'] = df['Date'].dt.strftime('%Y-%m')

    print('--- YEARLY (2024 - 2026) ---')
    print(pd.crosstab(df['Date'].dt.year, df['Category'], margins=True))

    print('\n--- MONTHLY (2024 - 2026) ---')
    print(pd.crosstab(df['Month'], df['Category'], margins=True))
except Exception as e:
    print(f"Error: {e}")
