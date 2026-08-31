from airchinstall.security import safe_excerpt


def test_terminal_excerpt_strips_ansi_and_redacts_secrets():
    raw = (
        "\x1b[31mfailed\x1b[0m\n"
        "OPENAI_API_KEY=sk-super-secret-value\n"
        "API Key: another-secret-value\n"
        "Authorization: Bearer token-value\n"
        "cryptsetup --key-file /tmp/private-key /dev/vda2\n"
        "tool --password cli-secret\n"
    )

    excerpt = safe_excerpt(raw)

    assert excerpt.startswith("failed")
    assert "\x1b" not in excerpt
    assert "super-secret" not in excerpt
    assert "token-value" not in excerpt
    assert "/tmp/private-key" not in excerpt
    assert "another-secret" not in excerpt
    assert "cli-secret" not in excerpt
    assert excerpt.count("[REDACTED]") == 5


def test_excerpt_is_bounded_from_the_tail():
    excerpt = safe_excerpt("prefix-" + "x" * 5000, limit=64)

    assert len(excerpt) == 64
    assert excerpt == "x" * 64
