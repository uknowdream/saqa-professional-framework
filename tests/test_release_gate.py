from scripts.qa_release_gate import MANDATORY


def test_release_certification_requires_all_quality_domains():
    assert MANDATORY == (
        "SAQA CI",
        "SAQA Contract Testing",
        "SAQA Accessibility",
        "SAQA Mobile Readiness",
        "SAQA k6 Performance",
    )
    assert len(MANDATORY) == len(set(MANDATORY))
