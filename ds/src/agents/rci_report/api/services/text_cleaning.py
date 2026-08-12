import re

# Confirmed live in rci_report_db_schema_findings.md: TrackWise bakes its own
# audit-log metadata directly into free-text field values, e.g.
# "10/31/2025 10:02 PM (GMT+5:30) added by R Anand (PID-008030): <actual text>".
# Only confirmed on one field (correction_or_remedial_action) on one example
# record — applied defensively to other long free-text TrackWise fields too.
# Multi-entry (a field edited more than once, with several timestamped prefixes
# concatenated) has not been verified against a real example; re.sub with no
# count limit strips every occurrence found, not just a leading one, so a
# multi-entry field degrades to its concatenated content rather than leaving
# earlier prefixes in place — see GAPS.md.
_AUDIT_LOG_PREFIX = re.compile(
    r"\d{1,2}/\d{1,2}/\d{2,4}\s+\d{1,2}:\d{2}\s*(?:AM|PM)\s*"
    r"\(GMT[+-]\d{1,2}:\d{2}\)\s*added by\s+.+?\(PID-\d+\)\s*:\s*",
    re.IGNORECASE,
)


def strip_audit_log_prefix(text: str) -> str:
    """Strip TrackWise's baked-in '<timestamp> added by <name> (PID-...): '
    prefix(es) from a free-text field value. Returns the input unchanged if no
    such prefix is present (most TrackWise fields don't carry one).
    """
    if not text:
        return text
    return _AUDIT_LOG_PREFIX.sub("", text).strip()
