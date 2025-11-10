# Stock Screener Data Module

A production-ready data fetching and storage module for identifying undervalued stocks near support levels. This module provides robust interfaces for retrieving stock data from Yahoo Finance and persisting it to a PostgreSQL or SQLite database.

## Features

- **Data Fetching**: Retrieve stock fundamentals and 5 years of price history from Yahoo Finance
- **Intelligent Caching**: Local pickle-based caching with configurable expiry (default: 24 hours)
- **Error Handling**: Automatic retry logic with exponential backoff for network failures
- **Database Storage**: SQLAlchemy-based storage with PostgreSQL or SQLite support
- **Value Screening**: Built-in queries to find undervalued stocks by P/E, P/B ratios
- **Type Safety**: Comprehensive type hints throughout the codebase
- **Production Ready**: Connection pooling, logging, and proper error handling

## Project Structure

```
stock-screener/
├── src/
│   ├── __init__.py
│   ├── data/
│   │   ├── __init__.py
│   │   ├── fetcher.py       # Yahoo Finance data fetching with caching
│   │   └── storage.py       # PostgreSQL/SQLite storage layer
├── tests/
│   ├── __init__.py
│   └── test_fetcher.py      # Comprehensive test suite
├── requirements.txt         # Python dependencies
├── .env.example            # Environment configuration template
└── README.md               # This file
```

## Installation

### 1. Clone and Setup

```bash
cd stock-screener
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your configuration
```

For **local development** (easiest):
```bash
DATABASE_URL=sqlite:///./stock_screener.db
```

For **production** with PostgreSQL:
```bash
DATABASE_URL=postgresql://user:password@localhost:5432/stock_screener
```

### 3. PostgreSQL Setup (Optional)

If using PostgreSQL:

```bash
# Install PostgreSQL (macOS)
brew install postgresql
brew services start postgresql

# Create database
createdb stock_screener

# Or using psql
psql postgres
CREATE DATABASE stock_screener;
\q
```

## Usage Examples

### Basic Data Fetching

```python
from src.data import YahooFinanceFetcher

# Initialize fetcher
fetcher = YahooFinanceFetcher(cache_dir="./data/cache")

# Fetch fundamentals for a single stock
fundamentals = fetcher.fetch_fundamentals("AAPL")
print(f"P/E Ratio: {fundamentals['pe_ratio']}")
print(f"P/B Ratio: {fundamentals['pb_ratio']}")
print(f"Current Price: {fundamentals['current_price']}")

# Fetch 5 years of price history
prices = fetcher.fetch_price_history("AAPL", period="5y")
print(prices.head())
print(f"Total records: {len(prices)}")

# Fetch data for multiple stocks
tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
fundamentals_df, prices_df = fetcher.fetch_multiple(tickers)
print(f"Fetched data for {len(fundamentals_df)} stocks")
print(fundamentals_df[['ticker', 'pe_ratio', 'pb_ratio', 'current_price']])

# Clear cache for specific ticker or all
fetcher.clear_cache("AAPL")  # Clear AAPL cache only
fetcher.clear_cache()        # Clear all cache
```

### Database Storage

```python
from src.data import StockDatabase, YahooFinanceFetcher

# Initialize database (creates tables automatically)
db = StockDatabase()  # Uses DATABASE_URL from .env

# Fetch and save data
fetcher = YahooFinanceFetcher()

# Save fundamentals
fundamentals = fetcher.fetch_fundamentals("AAPL")
db.save_stock_fundamentals("AAPL", fundamentals)

# Save price history
prices = fetcher.fetch_price_history("AAPL", period="5y")
db.save_price_history("AAPL", prices)

# Retrieve data from database
latest = db.get_latest_fundamentals("AAPL")
print(f"Latest P/E: {latest['pe_ratio']}")

history = db.get_price_history("AAPL", "2023-01-01", "2024-01-01")
print(f"Retrieved {len(history)} price records")

# Find undervalued stocks
cheap_stocks = db.query_cheap_stocks(pe_max=15, pb_max=1.5)
print(f"Found {len(cheap_stocks)} undervalued stocks: {cheap_stocks}")

# Get all tickers in database
all_tickers = db.get_all_tickers()
print(f"Database contains {len(all_tickers)} stocks")
```

### Complete Workflow Example

```python
from src.data import YahooFinanceFetcher, StockDatabase

# Initialize
fetcher = YahooFinanceFetcher(cache_dir="./data/cache")
db = StockDatabase()

# Define stock universe
sp500_sample = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "JPM", "V", "JNJ"]

# Fetch and store data
print("Fetching data for S&P 500 sample...")
for ticker in sp500_sample:
    print(f"Processing {ticker}...")

    # Fetch fundamentals
    fundamentals = fetcher.fetch_fundamentals(ticker)
    if fundamentals:
        db.save_stock_fundamentals(ticker, fundamentals)

    # Fetch price history
    prices = fetcher.fetch_price_history(ticker, period="5y")
    if not prices.empty:
        db.save_price_history(ticker, prices)

# Screen for value stocks
print("\nScreening for undervalued stocks...")
value_stocks = db.query_cheap_stocks(pe_max=20, pb_max=3.0, min_market_cap=10_000_000_000)
print(f"Found {len(value_stocks)} value stocks: {value_stocks}")

# Analyze each value stock
for ticker in value_stocks:
    data = db.get_latest_fundamentals(ticker)
    print(f"\n{ticker} - {data['name']}")
    print(f"  P/E: {data['pe_ratio']:.2f}, P/B: {data['pb_ratio']:.2f}")
    print(f"  Price: ${data['current_price']:.2f}")
    print(f"  52W Range: ${data['week_52_low']:.2f} - ${data['week_52_high']:.2f}")
```

## API Reference

### YahooFinanceFetcher

#### Methods

- `fetch_fundamentals(ticker: str) -> Dict[str, any]`
  - Fetches fundamental data for a stock
  - Returns: Dict with P/E, P/B, debt-to-equity, FCF, price data
  - Cached for 24 hours by default

- `fetch_price_history(ticker: str, period: str = "5y") -> pd.DataFrame`
  - Fetches historical OHLCV data
  - Period options: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
  - Returns: DataFrame with Date, Open, High, Low, Close, Volume

- `fetch_multiple(tickers: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame]`
  - Fetches data for multiple stocks
  - Returns: (fundamentals_df, prices_df)

- `clear_cache(ticker: Optional[str] = None) -> None`
  - Clears cached data for ticker or all if None

### StockDatabase

#### Methods

- `save_stock_fundamentals(ticker: str, data: Dict[str, any]) -> None`
  - Saves fundamental data to database
  - Creates/updates stock entry automatically

- `save_price_history(ticker: str, df: pd.DataFrame) -> None`
  - Bulk inserts price history data
  - Handles duplicates gracefully

- `get_latest_fundamentals(ticker: str) -> Dict[str, any]`
  - Retrieves most recent fundamental data
  - Returns: Dict with all fundamental metrics

- `get_price_history(ticker: str, start_date: str, end_date: str) -> pd.DataFrame`
  - Retrieves price data for date range
  - Date format: 'YYYY-MM-DD'
  - Returns: DataFrame with OHLCV data

- `query_cheap_stocks(pe_max: float, pb_max: float, min_market_cap: Optional[float]) -> List[str]`
  - Queries undervalued stocks by criteria
  - Returns: List of ticker symbols

- `get_all_tickers() -> List[str]`
  - Returns list of all tickers in database

## Database Schema

### Tables

**stocks**
- `id`: Primary key
- `ticker`: Unique stock symbol (indexed)
- `name`: Company name
- `sector`: Industry sector
- `last_updated`: Last update timestamp

**fundamentals**
- `id`: Primary key
- `stock_id`: Foreign key to stocks
- `date`: Data date (indexed)
- `pe_ratio`, `pb_ratio`, `debt_equity`, `fcf_yield`
- `market_cap`, `current_price`, `week_52_high`, `week_52_low`
- `trailing_eps`, `forward_eps`, `dividend_yield`

**price_history**
- `id`: Primary key
- `stock_id`: Foreign key to stocks
- `date`: Trading date (indexed, unique with stock_id)
- `open`, `high`, `low`, `close`, `volume`

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/data tests/

# Run specific test file
pytest tests/test_fetcher.py

# Run with verbose output
pytest -v

# Run specific test
pytest tests/test_fetcher.py::test_fetch_fundamentals_success
```

## Error Handling

The module includes comprehensive error handling:

- **Network Failures**: Automatic retry with 3 attempts and 2-second delays
- **Invalid Tickers**: Graceful handling with logging
- **Missing Data**: Returns None/empty for missing fields with warnings
- **Database Errors**: Transaction rollback with detailed error messages
- **Cache Issues**: Fallback to API if cache fails

## Configuration

Environment variables (set in `.env`):

- `DATABASE_URL`: Database connection string
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `CACHE_DIR`: Cache directory path (default: ./data/cache)
- `CACHE_EXPIRY_HOURS`: Cache expiry time (default: 24)

## Performance Tips

1. **Use Caching**: Let the cache work - subsequent calls are instant
2. **Batch Operations**: Use `fetch_multiple()` for multiple stocks
3. **Database Pooling**: PostgreSQL with connection pooling for production
4. **Bulk Inserts**: `save_price_history()` uses bulk operations
5. **Index Queries**: Database is indexed on ticker and date columns

## Logging

All operations are logged with timestamps:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

Log levels:
- `INFO`: Successful operations, cache hits/misses
- `WARNING`: Missing data, cache failures
- `ERROR`: API failures, database errors

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'yfinance'"
**Solution**: Run `pip install -r requirements.txt`

### Issue: "Could not connect to PostgreSQL"
**Solution**: Use SQLite for local testing: `DATABASE_URL=sqlite:///./stock_screener.db`

### Issue: "No data returned for ticker"
**Solution**: Ticker may be invalid or delisted. Check ticker symbol on Yahoo Finance.

### Issue: "Cache directory permission denied"
**Solution**: Ensure write permissions: `chmod 755 ./data/cache`

## Contributing

To extend this module:

1. Add new methods to `YahooFinanceFetcher` for additional data sources
2. Add new tables to `storage.py` for different data types
3. Add new query methods to `StockDatabase` for screening criteria
4. Write tests for all new functionality

## License

MIT License - See LICENSE file for details

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the test files for usage examples
3. Check Yahoo Finance API documentation: https://pypi.org/project/yfinance/

## Roadmap

Future enhancements:
- [ ] Support for multiple data sources (Alpha Vantage, IEX Cloud)
- [ ] Technical indicators calculation (RSI, MACD, Bollinger Bands)
- [ ] Support level detection algorithms
- [ ] Real-time data streaming
- [ ] Async data fetching for improved performance
- [ ] Web dashboard for visualization
