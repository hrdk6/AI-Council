"""Tests for pure parsing/formatting logic."""

from frontend.parsing import decision_brief_text, parse_directive


class TestParseDirective:
    def test_full_directive_parses_all_sections(self):
        value = (
            "Recommendation\n"
            "Launch the product.\n"
            "\n"
            "Why this wins\n"
            "First-mover advantage.\n"
            "\n"
            "Execution plan\n"
            "Ship in Q3.\n"
        )
        sections = parse_directive(value)
        assert [h for h, _ in sections] == ["Recommendation", "Why this wins", "Execution plan"]
        assert sections[0][1] == "Launch the product."
        assert sections[2][1] == "Ship in Q3."

    def test_headings_with_colon_are_accepted(self):
        value = "Recommendation:\nAdopt the strategy."
        sections = parse_directive(value)
        assert sections == [("Recommendation", "Adopt the strategy.")]

    def test_headings_case_insensitive(self):
        value = "recommendation\nDo it."
        sections = parse_directive(value)
        assert sections == [("Recommendation", "Do it.")]

    def test_no_headings_falls_back_to_recommendation(self):
        value = "Just some free text."
        sections = parse_directive(value)
        assert sections == [("Recommendation", "Just some free text.")]

    def test_none_value_uses_fallback(self):
        sections = parse_directive(None)
        assert sections == [("Recommendation", "No final answer was returned.")]

    def test_empty_heading_content_uses_fallback(self):
        value = "Recommendation\n"
        sections = parse_directive(value)
        assert sections == [("Recommendation", "No details returned.")]

    def test_multi_line_content_preserved(self):
        value = "Execution plan\nStep one.\nStep two.\nStep three."
        sections = parse_directive(value)
        assert sections[0][1] == "Step one.\nStep two.\nStep three."


class TestDecisionBriefText:
    def test_full_result(self):
        result = {
            "question": "Should we expand?",
            "decision_charter": "Charter text.",
            "final_answer": "Answer text.",
        }
        text = decision_brief_text(result)
        assert "Should we expand?" in text
        assert "Charter text." in text
        assert "Answer text." in text

    def test_fallback_question_used_when_missing(self):
        text = decision_brief_text({"decision_charter": "c", "final_answer": "a"}, fallback_question="Fallback q")
        assert "Fallback q" in text

    def test_missing_values_use_defaults(self):
        text = decision_brief_text({})
        assert "Not recorded" in text
        assert "Not returned by the backend." in text
        assert "No final answer was returned." in text
