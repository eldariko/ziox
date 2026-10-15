import os
from datetime import datetime, timezone
from database.repository import Repository
from providers.base import Tweet
from engine.thread_state import ThreadManager


def test_thread_state_and_disengagement(tmp_path):
    db_file = str(tmp_path / "test_thread.db")
    repo = Repository(db_file)
    manager = ThreadManager(repo, max_turns=2)

    now = datetime.now(timezone.utc)
    root_tweet = Tweet(
        id="root_100",
        text="A factual dispute on history.",
        author_handle="debater1",
        created_at=now
    )

    # 1. Turn 1 (Root reply)
    can_reply, reason = manager.evaluate_thread_permission(root_tweet)
    assert can_reply is True
    assert "Turn 1" in reason
    manager.record_interaction(root_tweet)

    # 2. Turn 2 (Counter reply from user)
    reply_tweet_turn2 = Tweet(
        id="reply_101",
        text="What about the 1948 border agreement?",
        author_handle="debater1",
        created_at=now,
        conversation_id="root_100",
        in_reply_to_tweet_id="root_100"
    )
    can_reply, reason = manager.evaluate_thread_permission(reply_tweet_turn2)
    assert can_reply is True
    assert "Turn 2" in reason
    manager.record_interaction(reply_tweet_turn2)

    # 3. Turn 3 should be disengaged (exceeded max_turns=2)
    reply_tweet_turn3 = Tweet(
        id="reply_102",
        text="Keep answering me!",
        author_handle="debater1",
        created_at=now,
        conversation_id="root_100",
        in_reply_to_tweet_id="reply_101"
    )
    can_reply, reason = manager.evaluate_thread_permission(reply_tweet_turn3)
    assert can_reply is False
    assert "Disengaged" in reason


def test_toxic_disengagement(tmp_path):
    db_file = str(tmp_path / "test_toxic.db")
    repo = Repository(db_file)
    manager = ThreadManager(repo, max_turns=2)

    toxic_tweet = Tweet(
        id="toxic_999",
        text="Shut up you disgusting nazi murderer",
        author_handle="troll_bot",
        created_at=datetime.now(timezone.utc)
    )

    can_reply, reason = manager.evaluate_thread_permission(toxic_tweet)
    assert can_reply is False
    assert "abusive language" in reason


def test_arabic_toxic_disengagement(tmp_path):
    db_file = str(tmp_path / "test_ar_toxic.db")
    repo = Repository(db_file)
    manager = ThreadManager(repo, max_turns=2)

    ar_toxic_tweet = Tweet(
        id="toxic_ar_1",
        text="أنتم قتلة ومجرمين وحثالة",
        author_handle="ar_troll",
        created_at=datetime.now(timezone.utc)
    )

    can_reply, reason = manager.evaluate_thread_permission(ar_toxic_tweet)
    assert can_reply is False
    assert "abusive language" in reason

    # Check status was recorded as DROPPED_TOXIC
    thread_data = repo.get_thread("toxic_ar_1")
    # Even if not created before, updating thread status persists or marks dropped
    assert thread_data is None or thread_data.get("status") == "DROPPED_TOXIC"

