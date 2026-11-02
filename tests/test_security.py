import logging
from engine.security import mask_telegram_token, SensitiveDataRedactor, setup_secure_logging


def test_mask_telegram_token_in_urls_and_strings():
    sample_url = "https://api.telegram.org/bot8847914934:AAEfRWayAqqQk1CUtoj9IJb7-qMqXbtwA9Q/getUpdates?timeout=0"
    masked = mask_telegram_token(sample_url)
    assert "8847914934:AAEfRWayAqqQk1CUtoj9IJb7-qMqXbtwA9Q" not in masked
    assert "https://api.telegram.org/bot[REDACTED]/getUpdates?timeout=0" == masked


def test_mask_telegram_token_with_none_and_other_types():
    assert mask_telegram_token(None) == ""
    assert mask_telegram_token(12345) == "12345"
    plain_url = "https://x.com/intent/tweet?text=hello"
    assert mask_telegram_token(plain_url) == plain_url


def test_sensitive_data_redactor_filter():
    redactor = SensitiveDataRedactor()
    
    # Test record with bot token in msg
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="HTTP Request: GET https://api.telegram.org/bot123456:ABC-DEF_12345/sendMessage",
        args=(),
        exc_info=None
    )
    redactor.filter(record)
    assert "123456:ABC-DEF_12345" not in record.msg
    assert "bot[REDACTED]" in record.msg

    # Test record with bot token in args
    record_args = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="Failed calling %s",
        args=("https://api.telegram.org/bot999999:SECRET_TOKEN/getMe",),
        exc_info=None
    )
    redactor.filter(record_args)
    assert "SECRET_TOKEN" not in record_args.args[0]
    assert "bot[REDACTED]" in record_args.args[0]


def test_setup_secure_logging_mutes_noisy_libraries():
    setup_secure_logging(logging.INFO)
    assert logging.getLogger("httpx").level >= logging.WARNING
    assert logging.getLogger("httpcore").level >= logging.WARNING
    assert logging.getLogger("urllib3").level >= logging.WARNING
