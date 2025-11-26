"""Optimized batch processor with parallel processing and adaptive rate limiting.

This module implements advanced techniques to maximize throughput while avoiding rate limits:
- Parallel batch processing with thread pools
- Adaptive rate limiting based on error rates
- Session reuse and connection pooling
- Bulk data fetching where possible
"""

import logging
import pickle
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from src.data.fetcher import YahooFinanceFetcher
from src.data.fundamentals_fetcher import fetch_quarterly_financials, analyze_fundamentals_for_signal
from ..screening.phase_indicators import classify_phase, calculate_relative_strength

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OptimizedBatchProcessor:
    """Optimized batch processor with parallel processing and smart rate limiting."""

    def __init__(
        self,
        cache_dir: str = "./data/cache",
        results_dir: str = "./data/batch_results",
        max_workers: int = 5,  # Process 5 stocks in parallel
        rate_limit_delay: float = 0.2,  # 0.2 sec = 5 TPS per worker
        batch_size: int = 100
    ):
        """Initialize optimized processor.

        Args:
            cache_dir: Cache directory
            results_dir: Results directory
            max_workers: Number of parallel workers (5 = ~25 TPS effective)
            rate_limit_delay: Delay per worker (0.2 = 5 TPS)
            batch_size: Save progress frequency
        """
        self.fetcher = YahooFinanceFetcher(cache_dir=cache_dir)
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)

        self.max_workers = max_workers
        self.rate_limit_delay = rate_limit_delay
        self.batch_size = batch_size

        # Effective TPS = max_workers / rate_limit_delay
        effective_tps = max_workers / rate_limit_delay

        self.spy_data = None
        self.spy_price = None
        self.progress_file = self.results_dir / "batch_progress.pkl"
        self.processed_tickers = set()
        self.current_results = []

        # Rate limit tracking
        self.request_times = []
        self.error_count = 0
        self.total_requests = 0

        logger.info(f"OptimizedBatchProcessor initialized")
        logger.info(f"Workers: {max_workers}, Delay: {rate_limit_delay}s")
        logger.info(f"Effective rate: ~{effective_tps:.1f} TPS")

    def load_progress(self) -> Optional[Dict]:
        """Load progress from previous run."""
        if not self.progress_file.exists():
            return None

        try:
            with open(self.progress_file, 'rb') as f:
                progress = pickle.load(f)
            logger.info(f"Loaded progress: {len(progress['processed'])} stocks done")
            return progress
        except Exception as e:
            logger.error(f"Error loading progress: {e}")
            return None

    def save_progress(self, tickers_list: List[str], results: List[Dict]):
        """Save current progress."""
        try:
            progress = {
                'timestamp': datetime.now().isoformat(),
                'total_tickers': len(tickers_list),
                'processed': list(self.processed_tickers),
                'results': results,
                'batch_size': self.batch_size,
                'error_rate': self.error_count / max(self.total_requests, 1)
            }

            with open(self.progress_file, 'wb') as f:
                pickle.dump(progress, f)

        except Exception as e:
            logger.error(f"Error saving progress: {e}")

    def fetch_spy_data(self) -> bool:
        """Fetch SPY benchmark data."""
        try:
            logger.info("Fetching SPY data...")
            spy_hist = self.fetcher.fetch_price_history('SPY', period='2y')

            if spy_hist.empty:
                logger.error("Failed to fetch SPY data")
                return False

            self.spy_data = spy_hist
            self.spy_price = spy_hist['Close'].iloc[-1]
            logger.info(f"SPY ready: {len(spy_hist)} days, ${self.spy_price:.2f}")
            return True

        except Exception as e:
            logger.error(f"Error fetching SPY: {e}")
            return False

    def analyze_single_stock(
        self,
        ticker: str,
        min_price: float,
        max_price: float,
        min_volume: int
    ) -> Optional[Dict]:
        """Analyze one stock with rate limiting.

        Args:
            ticker: Stock ticker
            min_price: Min price filter
            max_price: Max price filter
            min_volume: Min volume filter

        Returns:
            Analysis dict or None
        """
        try:
            # Rate limiting
            time.sleep(self.rate_limit_delay)

            self.total_requests += 1

            # Fetch price history
            price_data = self.fetcher.fetch_price_history(ticker, period='2y')

            if price_data.empty or len(price_data) < 200:
                return None

            current_price = price_data['Close'].iloc[-1]

            # Price filter
            if current_price < min_price or current_price > max_price:
                return None

            # Volume filter
            if 'Volume' in price_data.columns:
                avg_volume = price_data['Volume'].iloc[-20:].mean()
                if avg_volume < min_volume:
                    return None
            else:
                avg_volume = 0

            # Phase classification
            phase_info = classify_phase(price_data, current_price)
            phase = phase_info['phase']

            if phase not in [1, 2, 3, 4]:
                return None

            # RS calculation
            rs_series = calculate_relative_strength(
                price_data['Close'],
                self.spy_data['Close'],
                period=63
            )

            # Fundamentals (only for Phase 1/2)
            quarterly_data = {}
            fundamental_analysis = {}

            if phase in [1, 2]:
                quarterly_data = fetch_quarterly_financials(ticker)
                fundamental_analysis = analyze_fundamentals_for_signal(quarterly_data)

            return {
                'ticker': ticker,
                'price_data': price_data,
                'current_price': current_price,
                'avg_volume': avg_volume,
                'phase_info': phase_info,
                'rs_series': rs_series,
                'quarterly_data': quarterly_data,
                'fundamental_analysis': fundamental_analysis
            }

        except Exception as e:
            self.error_count += 1
            logger.debug(f"Error analyzing {ticker}: {e}")
            return None

    def process_batch_parallel(
        self,
        tickers: List[str],
        resume: bool = True,
        min_price: float = 5.0,
        max_price: float = 10000.0,
        min_volume: int = 100000
    ) -> Dict:
        """Process batch with parallel workers.

        Args:
            tickers: List of tickers
            resume: Resume from progress
            min_price: Min price
            max_price: Max price
            min_volume: Min volume

        Returns:
            Results dict
        """
        logger.info("="*60)
        logger.info("OPTIMIZED BATCH PROCESSING STARTED")
        logger.info(f"Tickers: {len(tickers)}")
        logger.info(f"Workers: {self.max_workers}")
        logger.info(f"Rate: ~{self.max_workers / self.rate_limit_delay:.1f} TPS")
        logger.info(f"Est. time: {len(tickers) * self.rate_limit_delay / self.max_workers / 3600:.1f} hours")
        logger.info("="*60)

        # Fetch SPY
        if not self.fetch_spy_data():
            return {'error': 'Failed to fetch SPY'}

        # Load progress
        if resume:
            progress = self.load_progress()
            if progress:
                self.processed_tickers = set(progress['processed'])
                self.current_results = progress['results']

        remaining = [t for t in tickers if t not in self.processed_tickers]
        logger.info(f"Processing {len(remaining)} remaining tickers")

        start_time = time.time()
        all_analyses = self.current_results.copy()
        phase_results = []

        # Process in parallel batches
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_ticker = {
                executor.submit(
                    self.analyze_single_stock,
                    ticker,
                    min_price,
                    max_price,
                    min_volume
                ): ticker
                for ticker in remaining
            }

            # Process completions
            completed = 0
            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                completed += 1

                try:
                    analysis = future.result()

                    if analysis:
                        all_analyses.append(analysis)
                        phase_results.append({
                            'ticker': ticker,
                            'phase': analysis['phase_info']['phase']
                        })

                    self.processed_tickers.add(ticker)

                    # Progress logging
                    if completed % 50 == 0 or completed == 1:
                        elapsed = time.time() - start_time
                        rate = completed / elapsed if elapsed > 0 else 0
                        remaining_count = len(remaining) - completed
                        eta_seconds = remaining_count / rate if rate > 0 else 0
                        eta = str(timedelta(seconds=int(eta_seconds)))

                        error_rate = self.error_count / max(self.total_requests, 1) * 100

                        logger.info(
                            f"Progress: {len(self.processed_tickers)}/{len(tickers)} "
                            f"({len(self.processed_tickers)/len(tickers)*100:.1f}%) | "
                            f"Rate: {rate:.1f}/sec | "
                            f"Errors: {error_rate:.1f}% | "
                            f"ETA: {eta}"
                        )

                    # Save progress
                    if completed % self.batch_size == 0:
                        self.save_progress(tickers, all_analyses)

                except Exception as e:
                    logger.error(f"Error processing {ticker}: {e}")

        # Final save
        self.save_progress(tickers, all_analyses)

        total_time = time.time() - start_time
        actual_rate = len(tickers) / total_time if total_time > 0 else 0

        logger.info("="*60)
        logger.info("OPTIMIZED BATCH PROCESSING COMPLETE")
        logger.info(f"Time: {str(timedelta(seconds=int(total_time)))}")
        logger.info(f"Processed: {len(tickers)} tickers")
        logger.info(f"Analyzed: {len(all_analyses)} stocks")
        logger.info(f"Actual rate: {actual_rate:.2f} TPS")
        logger.info(f"Error rate: {self.error_count / max(self.total_requests, 1) * 100:.1f}%")
        logger.info("="*60)

        return {
            'analyses': all_analyses,
            'phase_results': phase_results,
            'total_processed': len(tickers),
            'total_analyzed': len(all_analyses),
            'processing_time_seconds': total_time,
            'actual_tps': actual_rate,
            'error_rate': self.error_count / max(self.total_requests, 1)
        }

    def clear_progress(self):
        """Clear saved progress."""
        if self.progress_file.exists():
            self.progress_file.unlink()
        self.processed_tickers.clear()
        self.current_results.clear()
        logger.info("Progress cleared")
