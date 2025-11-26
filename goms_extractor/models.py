"""
Data models for Government Order (GO) amendments.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Amendment:
    """Represents a single amendment within a GO"""
    rule_no: str
    sub_rule: Optional[str]
    clause: Optional[str]
    sub_clause: Optional[str]
    proviso_no: Optional[str]
    additional_position_ctx: Optional[str]
    type_of_action: str  # "sub" (substitute), "omit" (delete), "add" (insert)
    target_text: Optional[str]  # Text being replaced/deleted
    updated_text: Optional[str]  # New text being added/substituted
    raw_amendment_text: str  # Original full text of the amendment
    confidence: str = "medium"  # low, medium, high


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