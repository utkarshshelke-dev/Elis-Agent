"""
Package: ir_domain_agent
Description: IR Domain Agent built on Google ADK.
             ADK discovers root_agent automatically when running:
               adk web        — interactive web UI
               adk api_server — REST API
Author: IR Team
"""
from .agent import root_agent

__all__ = ["root_agent"]
