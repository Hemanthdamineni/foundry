"""Backward-compat re-export — canonical store lives in foundry.core.store."""
from foundry.core.store import SqliteStore
from foundry.core.store.backend import StoreBackend

__all__ = ["SqliteStore", "StoreBackend"]