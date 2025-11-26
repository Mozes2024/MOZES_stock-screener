# START HERE - Quant Analysis Engine

## ✅ System Status: FULLY OPERATIONAL

Your autonomous Quant Analysis & Execution Engine is ready to use!

## 🚀 Quick Start (3 Steps)

### 1. Run a Quick Test

```bash
cd ~/Documents/stock-screener
./run_test.sh
```

This tests the system with 5 stocks (AAPL, MSFT, GOOGL, TSLA, NVDA).

### 2. Run Full Screening

```bash
./run_screen.sh
```

This screens all tickers in `config.yaml` (30+ stocks).

### 3. View Results

Results are saved to `./data/results/quant_screen_YYYYMMDD_HHMMSS.txt`

---

## 📊 What The System Does

The engine automatically:

1. **Fetches Data**
   - Price history (2 years)
   - Quarterly fundamentals (revenue, EPS, inventory)
   - SPY benchmark data

2. **Classifies Market Phase** (1-4)
   - Phase 1: Base Building (compression)
   - Phase 2: Uptrend/Breakout ✅ **BUY ZONE**
   - Phase 3: Distribution (topping)
   - Phase 4: Downtrend ❌ **SELL ZONE**

3. **Scores Stocks** (0-100)
   - Buy signals: ≥70 required
   - Sell signals: ≥60 required
   - Weighted scoring across technical + fundamental factors

4. **Generates Daily Report**
   - Benchmark summary (SPY + market breadth)
   - Buy list with fundamental snapshots
   - Sell list with breakdown analysis
   - Clean fallbacks ("NO BUYS TODAY" when appropriate)

---

## 🎯 Common Use Cases

### Daily Screening (After Market Close)

```bash
./run_screen.sh
```

### Screen Specific Stocks

```bash
./run_screen.sh --tickers AAPL MSFT GOOGL NVDA AMD TSLA
```

### Add Stocks to Your Watchlist

Edit `config.yaml`:

```yaml
stock_universe:
  - AAPL
  - MSFT
  # Add your tickers here
  - YOUR_TICKER
```

Then run: `./run_screen.sh`

---

## 📁 Important Files

| File | Purpose |
|------|---------|
| `run_test.sh` | ⭐ Quick test (5 stocks) |
| `run_screen.sh` | ⭐ Full screening |
| `config.yaml` | Stock universe & parameters |
| `QUICK_START.md` | Detailed usage guide |
| `QUANT_ENGINE_README.md` | Complete documentation |
| `IMPLEMENTATION_SUMMARY.md` | Technical details |

---

## 🔧 Customization

### Change Score Thresholds

Edit `config.yaml`:

```yaml
parameters:
  min_buy_score: 70    # Minimum buy signal score
  min_sell_score: 60   # Minimum sell signal score
```

### Change Market Breadth Requirement

```yaml
parameters:
  min_phase2_pct: 15.0  # Min % of stocks in Phase 2 for buys
```

### Change Volume Threshold

```yaml
parameters:
  volume_threshold: 1.5  # Breakout requires 1.5x avg volume
```

---

## 📖 Documentation

- **Quick Start**: [QUICK_START.md](QUICK_START.md) - Essential commands
- **Full Documentation**: [QUANT_ENGINE_README.md](QUANT_ENGINE_README.md) - Complete system guide
- **Technical Details**: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) - Implementation overview

---

## 💡 Example Output

```
============================================================
BENCHMARK SUMMARY
============================================================
SPY Trend Classification:
  Phase: 2 - Uptrend/Breakout
  Trend: Bullish
  Current Price: $675.02
  Confidence: 85%

Market Breadth: 40.0% in Phase 2
Market Regime: RISK-ON (Moderate)

============================================================
BUY LIST (Score >= 70)
============================================================

BUY #1: TICKER | Score: 85/100
Phase: 2
Breakout Price: $150.25
RS Slope: 2.35
Volume vs Avg: 1.8x

Reasons:
  • In Phase 2 (Uptrend)
  • Base Breakout at $150.25
  • Strong volume: 1.8x average
  • Excellent RS momentum: 2.35

FUNDAMENTAL SNAPSHOT
✓ Revenue: ACCELERATING (YoY: +25.3%)
✓ EPS: STRONG growth (YoY: +32.1%)
✓ Margins: EXPANDING (42.5%)
✓ Fundamentals SUPPORT technical breakout
```

---

## ⚠️ Important Notes

### Always Use the Shell Scripts

✅ **Correct**: `./run_test.sh` or `./run_screen.sh`

❌ **Wrong**: `python test_quant_engine.py` (missing virtual environment)

### Or Activate Virtual Environment First

```bash
source venv/bin/activate
python test_quant_engine.py
```

The shell scripts handle this automatically!

---

## 🎓 Understanding the Phase System

### Phase 2: BUY ZONE ✅

Stock transitions from Phase 1→2 or is already in Phase 2 with fresh breakout:
- Price closes above 50 SMA
- 50 SMA > 200 SMA
- Both SMAs rising
- Breakout above resistance
- Volume >150% of average
- RS vs SPY trending up

### Phase 3/4: SELL ZONE ❌

Stock transitions from Phase 2→3/4:
- Breakdown below 50 SMA on high volume
- 50 SMA flattening or declining
- RS rollover (negative 3-week slope)
- Failed breakout patterns

---

## 🔄 Daily Workflow

1. **Run after market close** (4-6 PM ET)
   ```bash
   ./run_screen.sh
   ```

2. **Review the report**
   - Check benchmark summary (market regime)
   - Review buy list (score ≥70)
   - Review sell list (score ≥60)
   - Read fundamental snapshots

3. **Take action**
   - Research buy candidates further
   - Consider sell signals for current positions
   - Follow your trading rules and risk management

---

## 🛠️ Troubleshooting

### "No module named 'numpy'"

You forgot to use the shell script or activate the virtual environment.

**Solution**: `./run_test.sh`

### "Permission denied"

The script isn't executable.

**Solution**: `chmod +x run_test.sh run_screen.sh`

### More Help

See [QUICK_START.md](QUICK_START.md) for detailed troubleshooting.

---

## 🎯 Next Steps

1. ✅ Run quick test: `./run_test.sh`
2. ✅ Review output and understand the format
3. ✅ Edit `config.yaml` to add your watchlist
4. ✅ Run full screening: `./run_screen.sh`
5. ✅ Set up daily cron job (optional)

---

## 📞 System Features

✅ Phase-based classification (1-4)
✅ Buy signals (Phase 2 breakouts)
✅ Sell signals (Phase 3/4 transitions)
✅ Weighted scoring (40/20/20/20)
✅ Fundamental analysis (quarterly data)
✅ Market breadth metrics
✅ Risk regime classification
✅ Data caching (24-hour expiry)
✅ Edge case handling
✅ Clean output formatting
✅ Results saved to files

---

## 🚀 You're Ready!

The system is fully operational and ready for daily use.

Start with: `./run_test.sh`

Then: `./run_screen.sh`

Happy screening! 📈
