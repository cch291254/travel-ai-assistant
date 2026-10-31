import logging

from app.logging_config import RedactingFormatter


def test_formatter_hides_sensitive_values():
    formatter = RedactingFormatter("%(message)s")
    record = logging.LogRecord(
        "app", logging.INFO, __file__, 1,
        "key sk-abcdefgh123456 手机13812345678 证件110101199001011234 Bearer token_a",
        None, None,
    )

    text = formatter.format(record)

    assert "sk-abcdefgh123456" not in text
    assert "13812345678" not in text
    assert "110101199001011234" not in text
    assert "token_a" not in text