"""Tests for LinkedIn person section helpers."""

from src.job_aggregator.providers.linkedin_browser.person_sections import (
    parse_person_sections,
    profile_url,
    section_url,
)


class TestPersonSections:

    def test_parse_person_sections_empty(self) -> None:
        requested, unknown = parse_person_sections(None)
        assert requested == []
        assert unknown == []

    def test_parse_person_sections_known_and_unknown(self) -> None:
        requested, unknown = parse_person_sections("experience, education, foo, posts")
        assert requested == ["experience", "education", "posts"]
        assert unknown == ["foo"]

    def test_profile_url_normalizes_input(self) -> None:
        assert profile_url("https://www.linkedin.com/in/jane/") == (
            "https://www.linkedin.com/in/jane/"
        )

    def test_section_url_builds_detail_path(self) -> None:
        assert section_url("jane", "experience") == (
            "https://www.linkedin.com/in/jane/details/experience/"
        )

    def test_section_url_builds_contact_overlay(self) -> None:
        assert section_url("jane", "contact_info") == (
            "https://www.linkedin.com/in/jane/overlay/contact-info/"
        )
