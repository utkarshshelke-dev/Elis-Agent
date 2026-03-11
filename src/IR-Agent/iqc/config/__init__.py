"""
Package: config
Description: Exports the settings singleton for use across the iqc_adk package.
Author: IQC Team
"""
from .settings import settings, Settings

__all__ = ["settings", "Settings"]
