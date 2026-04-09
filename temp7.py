import pandas as pd
df = pd.read_csv('backtest_v2024_results.csv', parse_dates=['Date'])
df = df[df['Date'].dt.year >= 2024].copy()

# Question 1: Monthly/Yearly PnL
df['MonthStr'] = df['Date'].dt.strftime('%Y - %b')
df['Year'] = df['Date'].dt.year

monthly_pnl = df.groupby('MonthStr')['PnL'].sum() * 65 # Qty
yearly_pnl = df.groupby('Year')['PnL'].sum() * 65

print("--- PnL (in INR, assuming 65 QTY lot) ---")
print("YEARLY:")
print(yearly_pnl.to_string())
print("\nMONTHLY:")
print(monthly_pnl.to_string())

# Question 2: Bull vs Bear Count
side_counts = df['Side'].value_counts()
print("\n--- Strategy Side Counts (2024 - 2026) ---")
print(side_counts.to_string())
