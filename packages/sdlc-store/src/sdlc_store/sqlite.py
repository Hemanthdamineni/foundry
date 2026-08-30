"""Backward-compat — delegate to the canonical store."""
from foundry.core.store.sqlite import SqliteStore
from foundry.core.store.backend import StoreBackend

__all__ = ["SqliteStore", "StoreBackend"]
