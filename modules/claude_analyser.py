"""
claude_analyser.py
Uses Claude API to extract land size details from property listings.
Now includes estimated land category and confidence score when no explicit acreage is stated.
"""

import time
import json
import re
import anthropic


SYSTEM_PROMPT = """You are a UK property analyst extracting land size information from estate agent listings.

Respond ONLY with valid JSON. No markdown, no explanation, no preamble.

Your task:
1. Extract explicit land/plot size if stated (convert to acres if in other units)
2. If no explicit size is given, estimate a category based on language clues
3. Rate your confidence in the land size estimate

Land category definitions:
- "under_half_acre": Small garden, typical suburban plot, "large garden" with no other signals
- "half_to_one_acre": Generous garden, "substantial grounds", "large plot"  
- "one_to_three_acres": Paddock, "grounds", smallholding language, equestrian mentions
- "three_to_ten_acres": Multiple paddocks, "estate", significant woodland/orchards mentioned
- "over_ten_acres": Farm, large estate, extensive landholdings
- "unknown": Genuinely cannot estimate

Confidence levels for land_size_acres (the numeric estimate):
- "explicit": Acreage stated directly in the listing
- "high": Strong language signals (paddock, smallholding, equestrian, specific measurements)
- "medium": Moderate signals (grounds, substantial garden, rural plot)
- "low": Weak signals (large garden, country setting only)
- "none": No meaningful signals

Return this exact JSON structure:
{
  "land_size_stated": "string or null — exact text from listing if size is mentioned",
  "land_size_acres": float or null — numeric acres if explicitly stated or highly confident conversion,
  "land_size_category": "one of the categories above",
  "land_size_confidence": "explicit/high/medium/low/none",
  "land_type": "string — e.g. paddock, formal gardens, woodland, arable, mixed, unknown",
  "land_signals": "brief note on what language led to this estimate",
  "renovation_needed": "Yes/No/Partial/Unknown",
  "renovation_notes": "string or null",
  "summary": "1-2 sentence summary of the property focusing on land and renovation"
}"""


USER_PROMPT_TEMPLATE = """Analyse this property listing and extract land size information:

TITLE: {title}
PRICE: {price}
ADDRESS: {address}
DESCRIPTION: {description}
KEY FEATURES: {features}
"""


def analyse_listings(listings: list[dict], api_key: str) -> list[dict]:
    """
    Use Claude to extract land size and renovation status from each listing.
    
    Args:
        listings: List of listing dicts (already keyword-filtered)
        api_key: Anthropic API key
    
    Returns:
        List of listings with Claude analysis fields added
    """
    client = anthropic.Anthropic(api_key=api_key)
    results = []
    
    for i, listing in enumerate(listings):
        try:
            prompt = USER_PROMPT_TEMPLATE.format(
                title=listing.get('title', 'Unknown'),
                price=listing.get('price', 'Unknown'),
                address=listing.get('address', 'Unknown'),
                description=(listing.get('description', '') or '')[:2000],  # cap length
                features=', '.join(listing.get('features', []) or [])
            )
            
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=600,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )
            
            raw = response.content[0].text.strip()
            
            # Strip markdown fences if present
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            
            analysis = json.loads(raw)
            
        except json.JSONDecodeError:
            analysis = _default_analysis("JSON parse error")
        except Exception as e:
            analysis = _default_analysis(str(e))
        
        enriched = dict(listing)
        enriched.update({
            'claude_land_stated': analysis.get('land_size_stated'),
            'claude_land_acres': analysis.get('land_size_acres'),
            'claude_land_category': analysis.get('land_size_category', 'unknown'),
            'claude_land_confidence': analysis.get('land_size_confidence', 'none'),
            'claude_land_type': analysis.get('land_type', 'unknown'),
            'claude_land_signals': analysis.get('land_signals', ''),
            'claude_renovation': analysis.get('renovation_needed', 'Unknown'),
            'claude_renovation_notes': analysis.get('renovation_notes', ''),
            'claude_summary': analysis.get('summary', ''),
        })
        
        # Best acres estimate: Claude's explicit value, or keyword-extracted value
        # (keyword extraction already ran in keyword_filter.py)
        keyword_acres = listing.get('_extracted_acres')
        claude_acres = enriched['claude_land_acres']
        enriched['best_acres_estimate'] = claude_acres or keyword_acres
        
        results.append(enriched)
        
        # Small delay to avoid rate limits
        if i < len(listings) - 1:
            time.sleep(0.15)
    
    return results


def _default_analysis(error_msg: str) -> dict:
    return {
        'land_size_stated': None,
        'land_size_acres': None,
        'land_size_category': 'unknown',
        'land_size_confidence': 'none',
        'land_type': 'unknown',
        'land_signals': f'Analysis error: {error_msg}',
        'renovation_needed': 'Unknown',
        'renovation_notes': None,
        'summary': 'Could not analyse this listing.',
    }
