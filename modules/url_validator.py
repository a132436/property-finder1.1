from urllib.parse import urlparse, parse_qs


SORT_LABELS = {
    "1": "Highest price",
    "2": "Most recent",
    "4": "Lowest price",
    "6": "Newest listed",
    "10": "Oldest listed",
}

PROPERTY_TYPE_LABELS = {
    "detached": "Detached",
    "semi-detached": "Semi-detached",
    "terraced": "Terraced",
    "flat": "Flat",
    "bungalow": "Bungalow",
    "land": "Land",
    "park home": "Park home",
}


def validate_rightmove_url(url: str) -> dict:
    """
    Validates a Rightmove search URL and returns a human-readable summary
    of the detected filters.
    """
    url = url.strip()

    parsed = urlparse(url)

    # Must be rightmove.co.uk
    if "rightmove.co.uk" not in parsed.netloc:
        return {
            "valid": False,
            "error": "This doesn't look like a Rightmove URL. Please paste a URL from rightmove.co.uk",
        }

    # Must be a search results page
    valid_paths = [
        "/property-for-sale/find.html",
        "/property-to-rent/find.html",
        "/commercial-property-for-sale/find.html",
    ]
    if not any(parsed.path.startswith(p) for p in valid_paths):
        return {
            "valid": False,
            "error": (
                "This looks like a Rightmove page but not a search results URL. "
                "Please go to Rightmove, run a search with your filters, then copy the URL from your browser's address bar."
            ),
        }

    params = parse_qs(parsed.query)

    def get_param(key):
        vals = params.get(key, [])
        return vals[0] if vals else None

    # Build price range string
    min_price = get_param("minPrice")
    max_price = get_param("maxPrice")
    if min_price and max_price:
        price_range = f"£{int(min_price):,} – £{int(max_price):,}"
    elif min_price:
        price_range = f"£{int(min_price):,}+"
    elif max_price:
        price_range = f"Up to £{int(max_price):,}"
    else:
        price_range = "Any"

    # Property type
    prop_types = params.get("propertyTypes", [])
    if prop_types:
        prop_type = ", ".join(
            PROPERTY_TYPE_LABELS.get(p.lower(), p.capitalize()) for p in prop_types
        )
    else:
        prop_type = "Any"

    # Bedrooms
    min_beds = get_param("minBedrooms")
    max_beds = get_param("maxBedrooms")
    if min_beds and max_beds:
        beds = f"{min_beds}–{max_beds}"
    elif min_beds:
        beds = f"{min_beds}+"
    elif max_beds:
        beds = f"Up to {max_beds}"
    else:
        beds = "Any"

    # Sort order
    sort_type = get_param("sortType")
    sort_label = SORT_LABELS.get(sort_type, "Default") if sort_type else "Default"

    # Other notable filters
    other_filters = []
    must_have = params.get("mustHave", [])
    for mh in must_have:
        for item in mh.split(","):
            item = item.strip()
            if item == "garden":
                other_filters.append("Garden")
            elif item == "parking":
                other_filters.append("Parking")
            elif item == "newHome":
                other_filters.append("New homes only")

    dont_show = params.get("dontShow", [])
    for ds in dont_show:
        for item in ds.split(","):
            item = item.strip()
            if item == "newHome":
                other_filters.append("Excl. new homes")
            elif item == "retirement":
                other_filters.append("Excl. retirement")
            elif item == "sharedOwnership":
                other_filters.append("Excl. shared ownership")

    tenure_types = params.get("tenureTypes", [])
    for tt in tenure_types:
        if "FREEHOLD" in tt.upper():
            other_filters.append("Freehold only")

    return {
        "valid": True,
        "summary": {
            "price_range": price_range,
            "property_type": prop_type,
            "min_bedrooms": beds,
            "sort_order": sort_label,
            "other_filters": other_filters,
        },
    }
