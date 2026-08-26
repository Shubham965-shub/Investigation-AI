"""SQL filter builder for new business requirements."""

from __future__ import annotations

import sys
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.config.settings import settings

# The RCI report/plan/evidence modules only ever know the app-level event
# type shown in the UI ("Deviation" / "OOS" / "OOT" / "OOS/OOT" / "Market
# Complaint"), not the DB's own qe_type values ("Deviation" / "Out Of
# Specification" / "Out of Trend" / "Complaint"). Only "Deviation" happens to
# be spelled the same both ways, which let every OOS/OOT/Market Complaint
# historical-search filter silently match zero rows (exact-match SQL, no
# raised error) while Deviation records worked — this is the reverse of
# backend/backend/db/field_mapping.py's QE_TYPE_TO_EVENT_TYPE (DB -> app),
# which ds/ has no access to (separate services, no cross-import).
APP_EVENT_TYPE_TO_QE_TYPE: dict[str, str | list[str]] = {
    "Deviation": "Deviation",
    "OOS": "Out Of Specification",
    "OOT": "Out of Trend",
    "OOS/OOT": ["Out Of Specification", "Out of Trend"],
    "Market Complaint": "Complaint",
}


def resolve_qe_type_filter(event_type: Optional[str]) -> Optional[str | list[str]]:
    """Translate an app-level event_type into the DB-native qe_type value(s)
    to filter on. Falls back to the input unchanged for anything not in the
    known set, rather than dropping the filter silently.
    """
    if event_type is None:
        return None
    return APP_EVENT_TYPE_TO_QE_TYPE.get(event_type, event_type)


@dataclass
class SearchFilters:
    """Encapsulates optional search filter parameters."""

    qe_type: Optional[str | list[str]] = None  # search_on parameter
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    locations: Optional[list[str]] = None  # sites parameter
    instruments: Optional[list[str]] = None
    materials: Optional[list[str]] = None
    sfg_code: Optional[list[str]] = None
    product_code: Optional[list[str]] = None  # sfg_code parameter
    # The record's own id, excluded from results — a "historical similar events"
    # search run using this record's own description as the query text otherwise
    # self-matches with near-perfect relevance once the record itself is persisted.
    exclude_id: Optional[str] = None





@dataclass
class WhereClause:
    """Holds a list of SQL WHERE fragments and their corresponding params."""

    fragments: list[str] = field(default_factory=list)
    params: list[Any] = field(default_factory=list)

    @property
    def sql(self) -> str:
        """Return combined WHERE clause or empty string."""
        if not self.fragments:
            return ""
        return " AND " + " AND ".join(self.fragments)

    @property
    def next_param_index(self) -> int:
        """Return the next $N parameter index (1-based, after existing params)."""
        return len(self.params) + 1


def parse_date_range(
    date_range: str,
    custom_from: Optional[str] = None,
    custom_to: Optional[str] = None,
) -> tuple[Optional[datetime], Optional[datetime]]:
    """
    Convert date range option to absolute datetime values.
    
    Parameters
    ----------
    date_range : str
        One of: last_7_days, last_30_days, last_90_days, last_6_months, 
        last_year, last_18_months, last_2_years, last_3_years, all, custom
    custom_from : str, optional
        ISO format date string for custom range start
    custom_to : str, optional
        ISO format date string for custom range end
        
    Returns
    -------
    tuple[Optional[datetime], Optional[datetime]]
        (date_from, date_to) or (None, None) if all
    """
    # Support both 'all' (new) and 'all_time' (legacy) for backward compatibility
    if date_range in ("all", "all_time"):
        return None, None
    
    if date_range == "custom":
        date_from = datetime.fromisoformat(custom_from) if custom_from else None
        date_to = datetime.fromisoformat(custom_to) if custom_to else None
        return date_from, date_to
    
    now = datetime.now()
    
    if date_range == "last_7_days":
        return now - timedelta(days=7), now
    elif date_range == "last_30_days":
        return now - timedelta(days=30), now
    elif date_range == "last_90_days":
        return now - timedelta(days=90), now
    elif date_range == "last_6_months":
        return now - timedelta(days=180), now
    elif date_range == "last_year":
        return now - timedelta(days=365), now
    elif date_range == "last_18_months":
        return now - timedelta(days=547), now  # 18 * 30.4 ≈ 547 days
    elif date_range == "last_2_years":
        return now - timedelta(days=730), now  # 2 * 365 = 730 days
    elif date_range == "last_3_years":
        return now - timedelta(days=1095), now  # 3 * 365 = 1095 days
    
    # Default to all if unknown
    return None, None


def build_filter_clause(
    filters: SearchFilters,
    param_offset: int = 1,
) -> WhereClause:
    """
    Build parameterised WHERE fragments from *filters*.

    Parameters
    ----------
    filters : SearchFilters
        The user / agent-supplied filters with new columns.
    param_offset : int
        The starting ``$N`` parameter index.  Set this to the number of
        positional parameters already consumed by the query (e.g. 1 if
        the query text is ``$1``).

    Returns
    -------
    WhereClause
        SQL fragments + params ready to be appended to a query.
    """
    clause = WhereClause()
    idx = param_offset + 1  # next available $N

    # Single value filters
    if filters.qe_type is not None:
        if isinstance(filters.qe_type, list):
            clause.fragments.append(f'"{settings.COLUMN_QE_TYPE}" = ANY(${idx})')
            clause.params.append(filters.qe_type)
        else:
            clause.fragments.append(f'"{settings.COLUMN_QE_TYPE}" = ${idx}')
            clause.params.append(filters.qe_type)
        idx += 1

    if filters.exclude_id is not None:
        # Table-qualified with "t": when SEARCH_DETAILS_TABLE is configured,
        # semantic_search.py joins details table "t" to vector table "v" ON
        # t.<COLUMN_ID> = v.<COLUMN_ID> -- both sides then have this column,
        # so an unqualified reference is ambiguous to Postgres. "t" is always
        # a valid alias for this column: it's the join's left side when a
        # details table is configured, and the sole table's own alias
        # otherwise.
        clause.fragments.append(f't."{settings.COLUMN_ID}"::text != ${idx}')
        clause.params.append(str(filters.exclude_id))
        idx += 1

    # Date range filters (date_opened column) — pass the real datetime object;
    # asyncpg needs an actual datetime/date instance for a timestamp column
    # comparison, not its string representation (str() previously broke every
    # caller that actually exercised date_from/date_to against a real DB).
    if filters.date_from is not None:
        clause.fragments.append(f'"{settings.COLUMN_DATE_OPENED}" >= ${idx}')
        clause.params.append(filters.date_from)
        idx += 1

    if filters.date_to is not None:
        clause.fragments.append(f'"{settings.COLUMN_DATE_OPENED}" <= ${idx}')
        clause.params.append(filters.date_to)
        idx += 1

    # Multi-value filters with "all" handling
    # Skip filter if list contains "all" (case-insensitive)
    
    if filters.locations and not any(loc.lower() == "all" for loc in filters.locations):
        clause.fragments.append(f'"{settings.COLUMN_LOCATION}" = ANY(${idx})')
        clause.params.append(filters.locations)
        idx += 1

    if filters.instruments and not any(inst.lower() == "all" for inst in filters.instruments):
        clause.fragments.append(f'"{settings.COLUMN_INSTRUMENT}" = ANY(${idx})')
        clause.params.append(filters.instruments)
        idx += 1

    if filters.materials and not any(mat.lower() == "all" for mat in filters.materials):
        clause.fragments.append(f'"{settings.COLUMN_MATERIAL}" = ANY(${idx})')
        clause.params.append(filters.materials)
        idx += 1

    if filters.sfg_code and not any(mat.lower() == "all" for mat in filters.sfg_code):
        clause.fragments.append(f'"{settings.COLUMN_SFG_CODE}" = ANY(${idx})')
        clause.params.append(filters.sfg_code)
        idx += 1
    return clause

