import re


# Default keywords that strongly suggest meaningful land
DEFAULT_KEYWORDS = [
    "acre", "acres", "acreage",
    "paddock", "paddocks",
    "grounds", "ground",
    "smallholding",
    "farmland", "farm land",
    "equestrian",
    "pasture", "pastureland",
    "meadow",
    "plot of land", "parcel of land",
    "estate",
    "orchard",
    "woodland",
    "grazing",
]

# Regex patterns for detecting acreage numbers in text
# Matches things like: "2 acres", "1.5 acres", "0.75 acre", "3/4 acre", "half an acre"
ACRE_PATTERNS = [
    r"(\d+\.?\d*)\s*acres?",                      # "2 acres", "1.5 acre"
    r"(\d+)\s*/\s*(\d+)\s*acre",                  # "3/4 acre"
    r"half\s+an?\s+acre",                          # "half an acre" → 0.5
    r"quarter\s+(?:of\s+an?\s+)?acre",             # "quarter of an acre" → 0.25
    r"three\s+quarters?\s+(?:of\s+an?\s+)?acre",   # "three quarters of an acre" → 0.75
]


def apply_keyword_filter(
    listings: list,
    keywords: list = None,
    min_acres: float = None,
) -> tuple[list, list]:
    """
    Filters listings by scanning description + key features for land keywords.

    Args:
        listings: normalised listings from apify_scraper
        keywords: list of keywords to match (uses DEFAULT_KEYWORDS if None)
        min_acres: if set, also require an acreage of at least this value

    Returns:
        (survivors, rejected) — two lists of listings
    """
    if keywords is None:
        keywords = DEFAULT_KEYWORDS

    # Normalise keywords for matching
    keywords_lower = [k.lower().strip() for k in keywords if k.strip()]

    survivors = []
    rejected = []

    for listing in listings:
        text = (listing.get("full_text") or "").lower()

        # ── Keyword match ─────────────────────────────────────────────────────
        matched = []
        for kw in keywords_lower:
            # Use word boundary matching for short keywords to avoid false positives
            # e.g. "land" shouldn't match "landlord"
            if len(kw) <= 5:
                pattern = r"\b" + re.escape(kw) + r"\b"
            else:
                pattern = re.escape(kw)

            if re.search(pattern, text):
                matched.append(kw)

        if not matched:
            rejected.append(listing)
            continue

        # ── Acreage extraction ────────────────────────────────────────────────
        acres_value = _extract_acres(text)
        listing["_matched_keywords"] = matched
        listing["_extracted_acres_raw"] = acres_value

        # If a minimum acreage is specified, check it
        if min_acres is not None:
            if acres_value is None or acres_value < min_acres:
                rejected.append(listing)
                continue

        survivors.append(listing)

    return survivors, rejected


def _extract_acres(text: str) -> float | None:
    """
    Attempts to extract the largest acreage value mentioned in the text.
    Returns None if no acreage is found.
    """
    text = text.lower()
    found_values = []

    # Numeric patterns: "2 acres", "1.5 acres"
    for match in re.finditer(r"(\d+\.?\d*)\s*acres?", text):
        try:
            found_values.append(float(match.group(1)))
        except ValueError:
            pass

    # Fraction: "3/4 acre"
    for match in re.finditer(r"(\d+)\s*/\s*(\d+)\s*acres?", text):
        try:
            found_values.append(float(match.group(1)) / float(match.group(2)))
        except (ValueError, ZeroDivisionError):
            pass

    # Word fractions
    if re.search(r"half\s+an?\s+acres?", text):
        found_values.append(0.5)
    if re.search(r"quarter\s+(?:of\s+an?\s+)?acres?", text):
        found_values.append(0.25)
    if re.search(r"three[\s\-]quarters?\s+(?:of\s+an?\s+)?acres?", text):
        found_values.append(0.75)

    return max(found_values) if found_values else None
