"""Thread State Machine and Disengagement Logic."""

import re
from typing import Tuple
from database.repository import Repository
from providers.base import Tweet

# Obvious harassment/slur patterns for instant disengagement
TOXIC_PATTERNS = [
    r"\bpig[s]?\b",
    r"\bmurderer[s]?\b",
    r"\bnazi[s]?\b",
    r"\bfuck\b",
    r"\bshit\b",
    r"\bshut\s*up\b",
    r"\bterrorist[s]?\b",
    r"\bcolonizer[s]?\b",
]

TOXIC_REGEX = re.compile("|".join(TOXIC_PATTERNS), re.IGNORECASE)


class ThreadManager:
    """Manages multi-turn conversation states and safety boundaries."""

    def __init__(self, repository: Repository, max_turns: int = 2):
        self.repo = repository
        self.max_turns = max_turns

    def is_toxic_or_bad_faith(self, text: str) -> bool:
        """Check for abusive language or bad faith trolling triggers."""
        return bool(TOXIC_REGEX.search(text))

    def evaluate_thread_permission(self, tweet: Tweet) -> Tuple[bool, str]:
        """
        Determine if the bot is allowed to reply to this tweet based on thread state.
        Returns: (can_reply: bool, reason: str)
        """
        # Step 1: Toxicity Check
        if self.is_toxic_or_bad_faith(tweet.text):
            root_id = tweet.conversation_id or tweet.id
            self.repo.update_thread_status(root_id, "DROPPED_TOXIC")
            return False, "Disengaged: abusive language or bad-faith trolling detected"

        root_id = tweet.conversation_id or tweet.id
        existing_thread = self.repo.get_thread(root_id)

        # Step 2: New thread
        if not existing_thread:
            return True, "Approved: New thread (Turn 1)"

        # Step 3: Check existing thread status & turn count
        status = existing_thread.get("status", "ACTIVE")
        if status != "ACTIVE":
            return False, f"Disengaged: thread status is {status}"

        current_turn = existing_thread.get("current_turn", 1)
        max_allowed = existing_thread.get("max_turns", self.max_turns)

        if current_turn >= max_allowed:
            self.repo.update_thread_status(root_id, "COMPLETED")
            return False, f"Disengaged: reached maximum thread turns ({current_turn}/{max_allowed})"

        return True, f"Approved: Continuing thread (Turn {current_turn + 1})"

    def record_interaction(self, tweet: Tweet) -> None:
        """Update or create thread interaction in the database."""
        root_id = tweet.conversation_id or tweet.id
        existing = self.repo.get_thread(root_id)
        if not existing:
            self.repo.create_thread(root_id, tweet.author_handle, max_turns=self.max_turns)
        else:
            self.repo.advance_thread_turn(root_id)
