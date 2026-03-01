import re
import json
import requests
import streamlit as st


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are a property analyst. You will be given a UK property listing and must extract 
specific information about the land and property. Respond ONLY with valid JSON — no preamble, no markdown, 
no explanation. Your response must be parseable by Python's json.loads()."""

EXTRACTION_PROMPT = """Analyse this UK property listing and extract the following information.

LISTING:
Address: {address}
Price: £{price}
Description: {description}
Key Features: {key_features}

Extract and return ONLY this JSON structure:
{{
  "land_size": "the land/plot size as stated (e.g. '2.5 acres', '1 acre paddock', 'approx 3 acres') or 'Not specified' if unclear",
  "land_size_acres": <numeric acres as a float, or null if cannot be determined>,
  "land_type": "description of land type (e.g. 'Paddock and orchard', 'Arable land', 'Formal gardens and paddock') or 'Not specified'",
  "renovation_needed": "Yes / No / Partial / Unknown — based on phrases like 'requires updating', 'in need of modernisation', 'recently renovated', 'move-in ready' etc.",
  "renovation_notes": "brief note on renovation status, or empty string",
  "summary": "1-2 sentence summary focusing on the land and property's key appeal for a family seeking rural living"
}}

Be precise about acreage. Only populate land_size_acres if you are confident of the numeric value."""


def run_claude_analysis(listing: dict) -> dict:
    """
    Sends a single listing to Claude for land size extraction and analysis.
    Returns the listing dict enriched with Claude's findings.
    """
    api_key = st.secrets.get("ANTHROPIC_API_KEY")
    if not api_key:
        # Return listing with error flag rather than crashing
        listing["_claude_error"] = "ANTHROPIC_API_KEY not in secrets"
        listing["land_size"] = "Error — no API key"
        listing["land_size_acres"] = None
        listing["land_type"] = "—"
        listing["renovation_needed"] = "Unknown"
        listing["renovation_notes"] = ""
        listing["summary"] = "Claude API key not configured."
        return listing

    # Build the prompt
    key_features_text = "\n".join(
        f"- {f}" for f in (listing.get("keyFeatures") or [])
    ) or "None listed"

    user_prompt = EXTRACTION_PROMPT.format(
        address=listing.get("address", "Unknown"),
        price=f"{listing.get('price', 0):,}",
        description=listing.get("description", "No description available")[:3000],
        key_features=key_features_text[:500],
    )

    payload = {
        "model": MODEL,
        "max_tokens": 500,
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": user_prompt}
        ],
    }

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        resp = requests.post(ANTHROPIC_API_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["content"][0]["text"].strip()
    except requests.RequestException as e:
        listing["_claude_error"] = str(e)
        listing.update(_error_defaults())
        return listing
    except (KeyError, IndexError) as e:
        listing["_claude_error"] = f"Unexpected Claude response format: {e}"
        listing.update(_error_defaults())
        return listing

    # Parse JSON response
    try:
        # Strip markdown fences if Claude wrapped the JSON anyway
        clean = re.sub(r"```(?:json)?|```", "", raw_text).strip()
        extracted = json.loads(clean)
    except json.JSONDecodeError as e:
        listing["_claude_error"] = f"JSON parse error: {e}. Raw: {raw_text[:200]}"
        listing.update(_error_defaults())
        return listing

    # Merge extracted fields into listing
    listing["land_size"] = extracted.get("land_size", "Not specified")
    listing["land_size_acres"] = extracted.get("land_size_acres")
    listing["land_type"] = extracted.get("land_type", "Not specified")
    listing["renovation_needed"] = extracted.get("renovation_needed", "Unknown")
    listing["renovation_notes"] = extracted.get("renovation_notes", "")
    listing["summary"] = extracted.get("summary", "")

    return listing


def _error_defaults() -> dict:
    return {
        "land_size": "Analysis failed",
        "land_size_acres": None,
        "land_type": "—",
        "renovation_needed": "Unknown",
        "renovation_notes": "",
        "summary": "Claude analysis failed for this listing.",
    }
