"""Declarative data quality checks for pandas DataFrames."""
from . import qatar  # noqa: F401  (registers the Qatar checks)
from .checks import REGISTRY, Check, ConfigError, Context, Result, register
from .readers import ReadError, read_table
from .suite import Report, Suite

__all__ = ["REGISTRY", "Check", "ConfigError", "Context", "ReadError", "Report", "Result", "Suite", "read_table", "register"]
__version__ = "0.1.0"
