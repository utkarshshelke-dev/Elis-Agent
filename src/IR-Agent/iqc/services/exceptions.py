"""
Module: services/exceptions.py
Description: Exception hierarchy for IQC Agent.
Author: IQC Team
"""
from __future__ import annotations


class IQCBaseException(Exception):
    """Base exception for all IQC Agent errors."""

class UserNotFoundError(IQCBaseException):
    """User ID not found in basic_profiles."""

class FounderRejectedError(IQCBaseException):
    """Founder account attempted investor portal."""

class ProfileLoadError(IQCBaseException):
    """Investor profile could not be loaded."""

class ProfileSaveError(IQCBaseException):
    """Qualification fields could not be saved."""

class DatabaseError(IQCBaseException):
    """PostgreSQL operation failed."""


__all__ = [
    "IQCBaseException", "UserNotFoundError", "FounderRejectedError",
    "ProfileLoadError", "ProfileSaveError", "DatabaseError",
]