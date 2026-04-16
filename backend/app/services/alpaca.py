"""Alpaca client factory and wrappers."""
from typing import Optional
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient

from app.models.account import AlpacaAccount, AccountMode
from app.security import decrypt_secret


def get_trading_client(account: AlpacaAccount) -> TradingClient:
    """Return a TradingClient for the given account."""
    api_secret = decrypt_secret(account.api_secret_enc)
    paper = account.mode == AccountMode.paper
    return TradingClient(
        api_key=account.api_key,
        secret_key=api_secret,
        paper=paper,
    )


def get_data_client(account: AlpacaAccount) -> StockHistoricalDataClient:
    """Return a StockHistoricalDataClient for the given account."""
    api_secret = decrypt_secret(account.api_secret_enc)
    return StockHistoricalDataClient(
        api_key=account.api_key,
        secret_key=api_secret,
    )


def get_base_url(mode: AccountMode) -> str:
    if mode == AccountMode.paper:
        return "https://paper-api.alpaca.markets"
    return "https://api.alpaca.markets"
