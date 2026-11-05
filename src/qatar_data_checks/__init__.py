"""Declarative data quality checks for pandas DataFrames."""
from .checks import REGISTRY, Check, ConfigError, Context, Result, register
from .readers import ReadError, read_table

__all__ = ["REGISTRY", "Check", "ConfigError", "Context", "ReadError", "Result", "read_table", "register"]
__version__ = "0.1.0"
