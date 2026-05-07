"""Deprecated Titan-core app entrypoint wrapper.

The canonical application namespace is now ``titan_battlebuddy``. This module
remains so existing imports and startup commands continue to work during the
staged migration.
"""

from titan_battlebuddy.main import app, debug_verified_web, health_check, root, seed_default_user

__all__ = ["app", "root", "health_check", "seed_default_user", "debug_verified_web"]
