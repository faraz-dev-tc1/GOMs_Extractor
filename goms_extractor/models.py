"""
Data models for Government Order (GO) amendments.
"""

from dataclasses import dataclass
from typing import List, Optional

@dataclass
class GoDocument:
    """Represents a complete GO document"""
    goms_no: str
    abstract: str
    references: List[str]
    notification: str
    amendment: List[Amendment]
    signed_by: str
    signed_to: str
    raw_text: str