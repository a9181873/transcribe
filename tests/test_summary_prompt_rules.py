from summary_prompt_rules import SUMMARY_GROUNDING_RULES, apply_summary_rules


def test_rules_require_traditional_chinese_and_no_invention():
    assert "繁體中文" in SUMMARY_GROUNDING_RULES
    assert "不得補寫、猜測或創造" in SUMMARY_GROUNDING_RULES
    assert "不得自行推定" in SUMMARY_GROUNDING_RULES


def test_rules_are_prepended_to_style_prompt():
    prompt = apply_summary_rules("STYLE PROMPT")

    assert prompt.startswith("# 全域摘要規則")
    assert prompt.endswith("STYLE PROMPT")
