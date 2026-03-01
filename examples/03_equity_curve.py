"""
範例 03 – 查詢 Equity Curve（淨值曲線）
=========================================

建立完整的交易記錄後，輸入每月收盤價，
再用 equity_curve() 生成月度淨值時間序列。

最終輸出：
  1. 終端機表格
  2. equity_curve.png（折線圖）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ledger import StockLedger, equity_curve, print_curve, plot_curve

DB  = Path(__file__).parent.parent / "data" / "ex03_equity.db"
PNG = Path(__file__).parent.parent / "data" / "equity_curve.png"
DB.unlink(missing_ok=True)

ledger = StockLedger(db_path=DB)

# ════════════════════════════════════════════════════════════════════════════
# 1. 現金
# ════════════════════════════════════════════════════════════════════════════
ledger.add_cash(2_000_000, date="2024-01-02", note="初始資本")

# ════════════════════════════════════════════════════════════════════════════
# 2. 交易
# ════════════════════════════════════════════════════════════════════════════
# 買進台積電（2330）
ledger.add_trade("2330", "buy",  qty=1_000, price=580, date="2024-01-15", commission=826)
# 買進鴻海（2317）
ledger.add_trade("2317", "buy",  qty=5_000, price=103, date="2024-02-01", commission=733)
# 部分了結台積電
ledger.add_trade("2330", "sell", qty=500,   price=900, date="2024-07-01", commission=1_991)

# ════════════════════════════════════════════════════════════════════════════
# 3. 輸入每月收盤價（用於 mark-to-market）
# ════════════════════════════════════════════════════════════════════════════
tsmc_prices = {
    "2024-01-31": 650,  "2024-02-29": 700,  "2024-03-29": 780,
    "2024-04-30": 810,  "2024-05-31": 850,  "2024-06-28": 880,
    "2024-07-31": 920,  "2024-08-30": 870,  "2024-09-30": 900,
    "2024-10-31": 940,  "2024-11-29": 960,  "2024-12-31": 1_000,
}
foxconn_prices = {
    "2024-01-31": 103,  "2024-02-29": 110,  "2024-03-29": 115,
    "2024-04-30": 108,  "2024-05-31": 112,  "2024-06-28": 118,
    "2024-07-31": 122,  "2024-08-30": 120,  "2024-09-30": 125,
    "2024-10-31": 130,  "2024-11-29": 128,  "2024-12-31": 135,
}

for date, close in tsmc_prices.items():
    ledger.add_price("2330", date, close)
for date, close in foxconn_prices.items():
    ledger.add_price("2317", date, close)

# ════════════════════════════════════════════════════════════════════════════
# 4. 當日快照（即時持倉）
# ════════════════════════════════════════════════════════════════════════════
snap = ledger.equity_snapshot(as_of="2024-12-31")
print("─" * 52)
print(f"  快照日期    : {snap['date']}")
print(f"  現金        : {snap['cash']:>14,.0f}")
print(f"  市值        : {snap['market_value']:>14,.0f}")
print(f"  總淨值      : {snap['total_equity']:>14,.0f}")
print()
for sym, info in snap["positions"].items():
    print(
        f"    {sym:<6}  {info['qty']:>6,.0f} 股"
        f"  × {info['price']:>6,.0f}"
        f"  = {info['market_value']:>12,.0f}"
    )
print("─" * 52)

# ════════════════════════════════════════════════════════════════════════════
# 5. 生成月度 Equity Curve
# ════════════════════════════════════════════════════════════════════════════
df = equity_curve(ledger, start="2024-01-31", end="2024-12-31", freq="ME")

print_curve(df, title="2024 月度淨值曲線")

# ════════════════════════════════════════════════════════════════════════════
# 6. 統計摘要
# ════════════════════════════════════════════════════════════════════════════
init_equity = df["total_equity"].iloc[0]
final_equity = df["total_equity"].iloc[-1]
total_return = (final_equity / init_equity - 1) * 100
max_dd = (df["total_equity"] / df["total_equity"].cummax() - 1).min() * 100
best_month = df["return_pct"].max()
worst_month = df["return_pct"].min()

print(f"  初始淨值  : {init_equity:>14,.0f}")
print(f"  期末淨值  : {final_equity:>14,.0f}")
print(f"  總報酬率  : {total_return:>+.2f}%")
print(f"  最大回撤  : {max_dd:>.2f}%")
print(f"  最佳單月  : {best_month:>+.2f}%")
print(f"  最差單月  : {worst_month:>+.2f}%")

# ════════════════════════════════════════════════════════════════════════════
# 7. 儲存圖表
# ════════════════════════════════════════════════════════════════════════════
try:
    path = plot_curve(df, output_path=str(PNG))
    print(f"\n  圖表已儲存：{path}")
except Exception as e:
    print(f"\n  （圖表略過：{e}）")
