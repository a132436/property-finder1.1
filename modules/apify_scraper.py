import time
import requests
import streamlit as st


ACTOR_ID = "jKpgGfgRfzrGgEMa8"
APIFY_BASE = "https://api.apify.com/v2"


def run_apify_scrape(search_url: str, max_items: int = 100) -> tuple[list, str | None]:
    """
    Runs the Rightmove scraper actor on Apify and returns a list of listings.
    Returns (listings, error_message). On success error_message is None.
    """
    api_token = st.secrets.get("APIFY_API_TOKEN")
    if not api_token:
        return [], "APIFY_API_TOKEN not found in secrets. Please add it to your Streamlit secrets."

    headers = {
        "Content-Type": "application/json",
    }

    # ── Start the actor run ───────────────────────────────────────────────────
    run_payload = {
        "listUrls": [{"url": search_url}],
        "maxItems": max_items,
        "fullPropertyDetails": True,   # ensures description text is included
        "proxy": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"],
        },
    }

    run_url = f"{APIFY_BASE}/acts/{ACTOR_ID}/runs?token={api_token}"

    try:
        resp = requests.post(run_url, json=run_payload, headers=headers, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        return [], f"Failed to start Apify run: {e}"

    run_data = resp.json()
    run_id = run_data.get("data", {}).get("id")
    if not run_id:
        return [], f"Apify didn't return a run ID. Response: {run_data}"

    # ── Poll for completion ───────────────────────────────────────────────────
    status_url = f"{APIFY_BASE}/actor-runs/{run_id}?token={api_token}"
    max_wait_seconds = 300  # 5 minutes
    poll_interval = 8
    elapsed = 0

    while elapsed < max_wait_seconds:
        time.sleep(poll_interval)
        elapsed += poll_interval

        try:
            status_resp = requests.get(status_url, timeout=15)
            status_resp.raise_for_status()
        except requests.RequestException as e:
            return [], f"Error polling Apify run status: {e}"

        status = status_resp.json().get("data", {}).get("status")

        if status == "SUCCEEDED":
            break
        elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
            return [], f"Apify run ended with status: {status}"
        # else still RUNNING — keep polling

    else:
        return [], "Apify run timed out after 5 minutes. Try reducing the number of listings."

    # ── Fetch results ─────────────────────────────────────────────────────────
    dataset_id = status_resp.json().get("data", {}).get("defaultDatasetId")
    if not dataset_id:
        return [], "Could not find Apify dataset ID after run completed."

    results_url = (
        f"{APIFY_BASE}/datasets/{dataset_id}/items"
        f"?token={api_token}&format=json&limit={max_items}"
    )

    try:
        results_resp = requests.get(results_url, timeout=30)
        results_resp.raise_for_status()
        listings = results_resp.json()
    except requests.RequestException as e:
        return [], f"Failed to fetch results from Apify dataset: {e}"
    except ValueError:
        return [], "Apify returned invalid JSON in results."

    # ── Normalise fields ──────────────────────────────────────────────────────
    normalised = []
    for item in listings:
        normalised.append(_normalise_listing(item))

    return normalised, None


def _normalise_listing(raw: dict) -> dict:
    """
    Normalises an Apify Rightmove listing into a consistent structure
    that the rest of the app expects.
    """
    # Price — handle various formats Apify may return
    price = raw.get("price") or raw.get("price_numeric") or 0
    if isinstance(price, str):
        price = int("".join(filter(str.isdigit, price)) or 0)

    # Description — may be nested
    description = (
        raw.get("description")
        or raw.get("fullDescription")
        or raw.get("summary")
        or ""
    )

    # Key features — list of bullet points from the listing
    key_features = raw.get("keyFeatures") or raw.get("key_features") or []
    if isinstance(key_features, str):
        key_features = [key_features]

    # Combine description and key features for keyword scanning
    full_text = description + " " + " ".join(key_features)

    # URL
    url = raw.get("url") or raw.get("propertyUrl") or ""
    if url and not url.startswith("http"):
        url = "https://www.rightmove.co.uk" + url

    return {
        "id": raw.get("id") or raw.get("propertyId") or "",
        "address": raw.get("address") or raw.get("displayAddress") or "Unknown address",
        "price": price,
        "bedrooms": raw.get("bedrooms") or raw.get("num_bedrooms"),
        "bathrooms": raw.get("bathrooms"),
        "propertyType": raw.get("propertyType") or "",
        "propertySubType": raw.get("propertySubType") or "",
        "description": description,
        "keyFeatures": key_features,
        "full_text": full_text,
        "listingDate": raw.get("firstVisibleDate") or raw.get("addedOrReduced") or "",
        "url": url,
        "latitude": raw.get("latitude"),
        "longitude": raw.get("longitude"),
        "postcode": raw.get("postcode") or "",
        "_raw": raw,  # keep original for debugging
    }
