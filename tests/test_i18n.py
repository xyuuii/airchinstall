from airchinstall.i18n import Messages


def test_missing_chinese_message_falls_back_to_english():
    messages = Messages(en={"goal": "Goal", "only_en": "Fallback"}, zh_cn={"goal": "目标"})

    assert messages.get("goal") == "目标"
    assert messages.get("only_en") == "Fallback"
