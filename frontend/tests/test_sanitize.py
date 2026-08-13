"""Tests for XSS sanitization utilities."""

from frontend.utils import escape_text, escape_attr, sanitize_directive_content, safe_member_value


class TestEscapeText:
    def test_escapes_html_characters(self):
        assert escape_text("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"

    def test_newlines_become_breaks(self):
        assert escape_text("line1\nline2") == "line1<br>line2"

    def test_none_becomes_empty_string(self):
        assert escape_text(None) == ""


class TestEscapeAttr:
    def test_quotes_escaped(self):
        assert escape_attr('say "hi"') == "say &quot;hi&quot;"

    def test_newlines_preserved(self):
        assert escape_attr("a\nb") == "a\nb"

    def test_none_becomes_empty_string(self):
        assert escape_attr(None) == ""


class TestSafeMemberValue:
    def test_returns_fallback_when_missing(self):
        assert safe_member_value({}, "missing", "fb") == "fb"

    def test_escapes_value(self):
        value = safe_member_value({"role_name": "<b>Bob</b>"}, "role_name")
        assert value == "&lt;b&gt;Bob&lt;/b&gt;"


class TestSanitizeDirectiveContent:
    def test_strips_scripts(self):
        out = sanitize_directive_content("<p>Hello</p><script>alert(1)</script>")
        assert "script" not in out
        assert "Hello" in out

    def test_removes_event_handlers(self):
        out = sanitize_directive_content('<a href="#" onclick="alert(1)">click</a>')
        assert "onclick" not in out

    def test_removes_javascript_urls(self):
        out = sanitize_directive_content('<a href="javascript:alert(1)">x</a>')
        assert "javascript:" not in out

    def test_allows_safe_rich_text(self):
        out = sanitize_directive_content("<strong>Bold</strong> and <em>italic</em>")
        assert "<strong>" in out
        assert "<em>" in out

    def test_none_input_safe(self):
        assert sanitize_directive_content(None) == ""
