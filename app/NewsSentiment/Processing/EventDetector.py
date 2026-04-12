import re
from typing import Optional

class EventDetector:
    """
    Phase 1: Regex-based event classification.
    Transparent, debuggable, and fast.
    Phase 2 upgrade: fine-tuned BERT classifier (same output contract).
    """
    EventPatterns = {
        'EARNINGS_RESULT': [
            r'Q[1-4]\s+results?',
            r'quarterly\s+(profit|revenue|earnings)',
            r'net\s+profit\s+(rose|fell|declined|surged)',
            r'PAT\s+(jumps?|drops?|rises?)',
        ],
        'AGM_NOTICE': [r'annual\s+general\s+meeting', r'\bAGM\b'],
        'DIVIDEND':   [r'dividend\s+of\s+[\u20B9Rs\.]+', r'interim\s+dividend'],
        'BOARD_MEETING': [r'board\s+(of\s+directors\s+)?meeting'],
        'MERGER_ACQUISITION': [r'merger', r'acquisition', r'amalgamation'],
        'RIGHTS_ISSUE': [r'rights\s+issue', r'rights\s+entitlement'],
        'BLOCK_DEAL':   [r'block\s+deal', r'bulk\s+deal'],
        'INSIDER_TRADING': [r'insider\s+trading', r'SEBI.*ban'],
    }

    def ClassifyEvent(self, Text: str) -> Optional[str]:
        for EventType, Patterns in self.EventPatterns.items():
            for Pattern in Patterns:
                if re.search(Pattern, Text, re.IGNORECASE):
                    return EventType
        return None
