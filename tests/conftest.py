"""
Global pytest configuration and environment isolation.
Ensures external network dispatchers (like Telegram) default to disabled during unit testing
regardless of local developer .env values.
"""

import os
import pytest

# Ensure tests don't leak external dispatchers unless explicitly enabled by a test
os.environ["TELEGRAM_REVIEW_ENABLED"] = "false"
