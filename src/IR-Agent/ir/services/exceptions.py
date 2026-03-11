"""
Module: services/exceptions.py
Description: Exception hierarchy for IR Domain Agent.
Author: IR Team
"""
from __future__ import annotations


class IRBaseException(Exception):
    """Base exception for all IR Domain Agent errors."""

class SessionNotFoundError(IRBaseException):
    """Raised when no session exists for a given user_id."""

class SessionExpiredError(IRBaseException):
    """Raised when a session has exceeded the TTL."""

class IQCCallError(IRBaseException):
    """Raised when the HTTP call to the IQC Agent Engine fails."""

class IQCSessionCreateError(IRBaseException):
    """Raised when creating a new IQC Agent Engine session fails."""

class DatabaseError(IRBaseException):
    """Raised when a PostgreSQL operation fails unexpectedly."""

class AuthTokenError(IRBaseException):
    """Raised when obtaining a Google OAuth2 Bearer token fails."""


__all__ = [
    "IRBaseException", "SessionNotFoundError", "SessionExpiredError",
    "IQCCallError", "IQCSessionCreateError", "DatabaseError", "AuthTokenError",
]