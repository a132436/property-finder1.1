"""
keyword_filter.py
Scans listing descriptions for land-related keywords and extracts acreage.
Tightened to reduce false positives (landlord, acreage of surrounding area, etc.)
"""

import re


# Keywords that strongly suggest meaningful land/plot size
# Each is a (pattern, weight) tuple - weight used for sorting confidence
LAND_KEYWORDS = [
    # High-confidence: almost always means real land
    (r'\bpaddock\b', 'high'),
    (r'\bsmallholding\b', 'high'),
    (r'\bequestrian\b', 'high'),
    (r'\borchard\b', 'high'),
    (r'\bpasture\b', 'high'),
    (r'\bmeadow\b', 'high'),
    (r'\bstabling\b', 'high'),
    (r'\bstables?\b', 'high'),
    (r'\bbarn\b', 'high'),
    (r'\boutbuilding\b', 'high'),
    (r'\bcoppice\b', 'high'),
    (r'\bwoodland\b', 'high'),
    (r'\bgrounds\b', 'high'),
    (r'\bestate\b', 'high'),
    (r'\bsmallhold', 'high'),

    # Medium-confidence: usually land but can appear in other contexts
    (r'\bplot\b', 'medium'),
    (r'\bacres?\b', 'medium'),        # "acres" but NOT "acreage of the area" - handled below
    (r'\bhectares?\b', 'medium'),
    (r'\bplot of land\b', 'high'),
    (r'\bparcel of land\b', 'high'),
    (r'\bpiece of land\b', 'high'),
    (r'\bstrip of land\b', 'medium'),

    # Lower-confidence: vague but worth flagging
    (r'\bextensive garden', 'medium'),
    (r'\blarge garden', 'low'),
    (r'\bsubstantial garden', 'medium'),
    (r'\bprivate garden', 'low'),
    (r'\bmature garden', 'low'),
    (r'\brural setting\b', 'low'),
    (r'\bcountry setting\b', 'low'),
    (r'\bcountry property\b', 'low'),
    (r'\brural property\b', 'low'),
]

# Patterns that look like land keywords but aren't
FALSE_POSITIVE_PATTERNS = [
    r'\blandlord\b',
    r'\blandlady\b',
    r'\blandmark\b',
    r'\blandscape\b',       # "landscaped garden" is fine, but "landscape views" is not land
    r'\bstable employment\b',
    r'\bstable income\b',
    r'\bstable condition\b',
    r'\bplot your\b',       # "plot your journey"
    r'\bplot number\b',
    r'\bcouncil\s+estate\b',  # council estate ≠ country estate
    r'\bestate agent\b',
    r'\beach estate\b',     # "beach estate" is an agent name
]

# Acreage extraction patterns (most specific first)
ACRE_PATTERNS = [
    # "3.5 acres", "0.75 acres", "1 acre"
    (r'(\d+\.?\d*)\s*acres?', lambda m: float(m.group(1))),
    # "3/4 acre", "1/2 acre"
    (r'(\d+)\s*/\s*(\d+)\s*acres?', lambda m: float(m.group(1)) / float(m.group(2))),
    # Word fractions: "half an acre", "quarter of an acre", "three quarters of an acre"
    (r'three[\s-]quarters?\s+(?:of\s+an?\s+)?acres?', lambda m: 0.75),
    (r'half\s+an?\s+acres?', lambda m: 0.5),
    (r'quarter\s+(?:of\s+an?\s+)?acres?', lambda m: 0.25),
    # "approximately 2 acres", "around 1.5 acres"
    (r'(?:approximately|approx|around|circa|c\.)\s*(\d+\.?\d*)\s*acres?', lambda m: float(m.group(1))),
    # Hectares (1 hectare = 2.471 acres)
    (r'(\d+\.?\d*)\s*hectares?', lambda m: float(m.group(1)) * 2.471),
    # Square metres as a proxy for plot size (unusual but possible)
    # e.g. "plot of 4,000 sq m" ≈ 1 acre
    (r'(\d[\d,]*)\s*sq(?:uare)?\s*m(?:etres?|eters?)\b', lambda m: float(m.group(1).replace(',', '')) / 4047),
]


def _remove_false_positives(text: str) -> str:
    """Blank out known false-positive phrases so they don't trigger keyword matches."""
    cleaned = text
    for pattern in FALSE_POSITIVE_PATTERNS:
        cleaned = re.sub(pattern, ' [REMOVED] ', cleaned, flags=re.IGNORECASE)
    return cleaned


def _extract_acreage(text: str) -> float | None:
    """Return the largest acreage value found in text, or None."""
    values = []
    for pattern, converter in ACRE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                value = converter(match)
                if 0.01 < value < 10000:  # sanity bounds
                    values.append(value)
            except (ValueError, ZeroDivisionError):
                continue
    return max(values) if values else None


def _get_keyword_confidence(text: str) -> tuple[bool, str, list[str]]:
    """
    Returns (matched, highest_confidence_level, list_of_matched_keywords).
    confidence: 'high', 'medium', 'low', or None
    """
    cleaned = _remove_false_positives(text)
    matched_keywords = []
    confidence_rank = {'high': 3, 'medium': 2, 'low': 1}
    best_confidence = None
    best_rank = 0

    for pattern, confidence in LAND_KEYWORDS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            # Extract the actual word matched for display
            m = re.search(pattern, cleaned, re.IGNORECASE)
            matched_keywords.append(m.group(0).strip())
            rank = confidence_rank[confidence]
            if rank > best_rank:
                best_rank = rank
                best_confidence = confidence

    return len(matched_keywords) > 0, best_confidence, matched_keywords


def filter_by_keywords(listings: list[dict], min_confidence: str = 'low') -> list[dict]:
    """
    Filter listings to those containing land-related keywords.
    
    Args:
        listings: List of listing dicts with 'full_text' field
        min_confidence: Minimum keyword confidence to include ('low', 'medium', 'high')
    
    Returns:
        Filtered list with added fields:
            _keyword_matched: True
            _keyword_confidence: 'high'/'medium'/'low'
            _matched_keywords: list of matched terms
            _extracted_acres: float or None (from explicit text)
    """
    confidence_rank = {'high': 3, 'medium': 2, 'low': 1}
    min_rank = confidence_rank.get(min_confidence, 1)
    
    results = []
    for listing in listings:
        text = listing.get('full_text', '') or ''
        
        matched, confidence, keywords = _get_keyword_confidence(text)
        
        if not matched:
            continue
        
        if confidence_rank.get(confidence, 0) < min_rank:
            continue
        
        acres = _extract_acreage(text)
        
        enriched = dict(listing)
        enriched['_keyword_matched'] = True
        enriched['_keyword_confidence'] = confidence
        enriched['_matched_keywords'] = keywords
        enriched['_extracted_acres'] = acres  # None if not explicitly stated
        
        results.append(enriched)
    
    # Sort: explicit acreage first, then by keyword confidence
    def sort_key(l):
        has_acres = 0 if l['_extracted_acres'] is not None else 1
        conf_rank = -confidence_rank.get(l['_keyword_confidence'], 0)
        acres = -(l['_extracted_acres'] or 0)
        return (has_acres, conf_rank, acres)
    
    results.sort(key=sort_key)
    return results
