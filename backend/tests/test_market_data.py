"""Tests for market_data service — BarSet .data access pattern."""
from unittest.mock import MagicMock, patch

import pytest


class TestGetBarsCached:
    """Ensure get_bars_cached correctly accesses BarSet.data dict."""

    @patch("app.services.market_data._cache_get", return_value=None)
    @patch("app.services.market_data._cache_set")
    def test_bars_use_barset_data_attribute(self, mock_cache_set, mock_cache_get):
        """BarSet is not a dict — bars must be read from .data attr."""
        from app.services.market_data import get_bars_cached

        mock_bar_1 = MagicMock()
        mock_bar_1.timestamp = "2024-01-02T00:00:00Z"
        mock_bar_1.open = 400.0
        mock_bar_1.high = 405.0
        mock_bar_1.low = 399.0
        mock_bar_1.close = 402.0
        mock_bar_1.volume = 1_000_000.0

        mock_bar_2 = MagicMock()
        mock_bar_2.timestamp = "2024-01-03T00:00:00Z"
        mock_bar_2.open = 402.0
        mock_bar_2.high = 410.0
        mock_bar_2.low = 401.0
        mock_bar_2.close = 408.0
        mock_bar_2.volume = 1_200_000.0

        # Build a mock BarSet with .data (NOT a dict with .get)
        mock_barset = MagicMock()
        mock_barset.data = {"SPY": [mock_bar_1, mock_bar_2]}
        # Ensure .get() is NOT available — calling it would be a bug
        del mock_barset.get

        mock_client = MagicMock()
        mock_client.get_stock_bars.return_value = mock_barset

        mock_account = MagicMock()

        with patch("app.services.alpaca.get_data_client", return_value=mock_client):
            result = get_bars_cached(
                "SPY", "1Day", "2024-01-02", "2024-01-04", account=mock_account,
            )

        assert len(result) == 2
        assert result[0]["close"] == 402.0
        assert result[1]["close"] == 408.0
        assert result[0]["timestamp"] == "2024-01-02T00:00:00Z"

    @patch("app.services.market_data._cache_get", return_value=None)
    @patch("app.services.market_data._cache_set")
    def test_bars_missing_symbol_returns_empty(self, mock_cache_set, mock_cache_get):
        """If the requested symbol is not in BarSet.data, return []."""
        from app.services.market_data import get_bars_cached

        mock_barset = MagicMock()
        mock_barset.data = {}  # no symbols at all
        del mock_barset.get

        mock_client = MagicMock()
        mock_client.get_stock_bars.return_value = mock_barset

        mock_account = MagicMock()

        with patch("app.services.alpaca.get_data_client", return_value=mock_client):
            result = get_bars_cached(
                "SPY", "1Day", "2024-01-02", "2024-01-04", account=mock_account,
            )

        assert result == []

    def test_bars_no_account_returns_empty(self):
        """Without account, get_bars_cached short-circuits to []."""
        from app.services.market_data import get_bars_cached

        result = get_bars_cached("SPY", "1Day", "2024-01-02", "2024-01-04", account=None)
        assert result == []
