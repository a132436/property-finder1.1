import streamlit as st
import json
import re
import time
from urllib.parse import urlparse, parse_qs

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Property Finder",
    page_icon="🏡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .step-box {
        background: #f0f4f8;
        border-left: 4px solid #2563eb;
        border-radius: 6px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
    }
    .step-complete {
        border-left-color: #16a34a;
        background: #f0fdf4;
    }
    .step-waiting {
        border-left-color: #9ca3af;
        background: #f9fafb;
        opacity: 0.6;
    }
    .big-number {
        font-size: 2rem;
        font-weight: 700;
        color: #2563eb;
    }
    .warning-box {
        background: #fff7ed;
        border-left: 4px solid #f97316;
        border-radius: 6px;
        padding: 0.8rem 1rem;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

# ── Import modules ────────────────────────────────────────────────────────────
from modules.apify_scraper import run_apify_scrape
from modules.keyword_filter import filter_by_keywords as apply_keyword_filter
from modules.claude_analyser import analyse_listings as run_claude_analysis
from modules.commute_checker import run_commute_check
from modules.url_validator import validate_rightmove_url

# ── Session state initialisation ─────────────────────────────────────────────
defaults = {
    "step": 1,
    "url_validated": False,
    "url_summary": None,
    "raw_listings": None,
    "keyword_survivors": None,
    "claude_results": None,
    "commute_results": None,   # raw commute data — persists across re-runs
    "final_results": None,
    "input_url": "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🏡 Property Finder")
st.caption("Searches Rightmove for properties with land, scores by commute time and school quality.")
st.divider()

# ═════════════════════════════════════════════════════════════════════════════
# STEP 1 — URL INPUT & VALIDATION
# ═════════════════════════════════════════════════════════════════════════════
step1_class = "step-box step-complete" if st.session_state.step > 1 else "step-box"
st.markdown(f'<div class="{step1_class}">', unsafe_allow_html=True)
st.subheader("Step 1 — Paste your Rightmove search URL")
st.markdown("""
Set up your search on [Rightmove](https://www.rightmove.co.uk) with your preferred filters 
(price range, property type, region etc.), then copy the URL from your browser and paste it below.
""")

url_input = st.text_input(
    "Rightmove search URL",
    value=st.session_state.input_url,
    placeholder="https://www.rightmove.co.uk/property-for-sale/find.html?...",
    key="url_input_field",
)

if url_input and url_input != st.session_state.input_url:
    st.session_state.input_url = url_input
    st.session_state.url_validated = False
    st.session_state.url_summary = None
    st.session_state.step = 1

col1, col2 = st.columns([1, 4])
with col1:
    validate_btn = st.button("🔍 Validate URL", disabled=not url_input)

if validate_btn and url_input:
    with st.spinner("Checking URL..."):
        result = validate_rightmove_url(url_input)
    if result["valid"]:
        st.session_state.url_validated = True
        st.session_state.url_summary = result["summary"]
    else:
        st.error(f"❌ {result['error']}")
        st.session_state.url_validated = False

if st.session_state.url_validated and st.session_state.url_summary:
    st.success("✅ URL looks good!")
    s = st.session_state.url_summary
    cols = st.columns(4)
    cols[0].metric("Price range", s.get("price_range", "Any"))
    cols[1].metric("Property type", s.get("property_type", "Any"))
    cols[2].metric("Min bedrooms", s.get("min_bedrooms", "Any"))
    cols[3].metric("Sort order", s.get("sort_order", "Default"))
    if s.get("other_filters"):
        st.info(f"Additional filters detected: {', '.join(s['other_filters'])}")

    if st.session_state.step == 1:
        st.markdown('<div class="warning-box">👆 Happy with the search parameters above? Click below to proceed to scraping.</div>', unsafe_allow_html=True)
        if st.button("✅ Confirmed — proceed to scraping →", type="primary"):
            st.session_state.step = 2
            st.rerun()

st.markdown('</div>', unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════════
# STEP 2 — APIFY SCRAPE
# ═════════════════════════════════════════════════════════════════════════════
if st.session_state.step >= 2:
    step2_class = "step-box step-complete" if st.session_state.step > 2 else "step-box"
    st.markdown(f'<div class="{step2_class}">', unsafe_allow_html=True)
    st.subheader("Step 2 — Scrape listings from Rightmove")
    st.markdown("Apify will fetch the full details of every listing matching your search, including the description text.")

    max_listings = st.slider(
        "Maximum listings to fetch",
        min_value=10, max_value=500, value=100, step=10,
        help="More listings = more thorough but slower. 100 is a good starting point.",
        disabled=st.session_state.step > 2,
    )

    if st.session_state.step == 2 and st.session_state.raw_listings is None:
        if st.button("🚀 Run Apify scrape", type="primary"):
            with st.spinner(f"Scraping up to {max_listings} listings from Rightmove... (this takes 1–3 minutes)"):
                listings, error = run_apify_scrape(
                    st.session_state.input_url,
                    max_items=max_listings,
                )
            if error:
                st.error(f"❌ Scrape failed: {error}")
            else:
                st.session_state.raw_listings = listings

    if st.session_state.raw_listings is not None:
        listings = st.session_state.raw_listings
        st.success(f"✅ Scrape complete — {len(listings)} listings retrieved")

        # Preview table
        preview_data = []
        for l in listings[:10]:
            preview_data.append({
                "Address": l.get("address", "—"),
                "Price": f"£{l.get('price', 0):,}" if l.get("price") else "—",
                "Beds": l.get("bedrooms", "—"),
                "Type": l.get("propertySubType", l.get("propertyType", "—")),
                "Listed": l.get("listingDate", "—"),
            })

        st.markdown(f"**Preview (first {min(10, len(listings))} of {len(listings)} listings):**")
        st.dataframe(preview_data, use_container_width=True)

        if len(listings) > 10:
            st.caption(f"...and {len(listings) - 10} more listings not shown in preview.")

        if st.session_state.step == 2:
            st.markdown('<div class="warning-box">👆 Does the data above look right? Check addresses, prices and property types before proceeding.</div>', unsafe_allow_html=True)
            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("✅ Confirmed — proceed to keyword filter →", type="primary"):
                    st.session_state.step = 3
                    st.rerun()
            with col2:
                if st.button("🔄 Re-run scrape"):
                    st.session_state.raw_listings = None
                    st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════════
# STEP 3 — KEYWORD FILTER
# ═════════════════════════════════════════════════════════════════════════════
if st.session_state.step >= 3:
    step3_class = "step-box step-complete" if st.session_state.step > 3 else "step-box"
    st.markdown(f'<div class="{step3_class}">', unsafe_allow_html=True)
    st.subheader("Step 3 — Keyword filter (free)")
    st.markdown("""
    Filters listings by scanning description text for land-related keywords.
    Only listings that pass this step will be sent to Claude — keeping API costs minimal.
    """)

    default_keywords = "acre, acres, acreage, paddock, paddocks, land, grounds, smallholding, farmland, equestrian, pasture, meadow, plot, estate"

    if st.session_state.step == 3:
        keyword_input = st.text_area(
            "Keywords to search for (comma-separated)",
            value=default_keywords,
            height=80,
            help="Any listing whose description or key features contain at least one of these words will be kept.",
        )
        min_land_hint = st.selectbox(
            "Also require a specific acreage mention?",
            options=["No — keep all keyword matches", "Yes — must mention at least 0.5 acres", "Yes — must mention at least 1 acre", "Yes — must mention at least 2 acres"],
            index=0,
        )

        if st.button("🔎 Apply keyword filter", type="primary"):
            keywords = [k.strip().lower() for k in keyword_input.split(",") if k.strip()]
            min_acres = None
            if "0.5" in min_land_hint:
                min_acres = 0.5
            elif "1 acre" in min_land_hint:
                min_acres = 1.0
            elif "2 acres" in min_land_hint:
                min_acres = 2.0

            survivors, rejected = apply_keyword_filter(
                st.session_state.raw_listings,
                keywords=keywords,
                min_acres=min_acres,
            )
            st.session_state.keyword_survivors = survivors
            st.rerun()

    if st.session_state.keyword_survivors is not None:
        survivors = st.session_state.keyword_survivors
        total = len(st.session_state.raw_listings)
        kept = len(survivors)
        rejected = total - kept

        col1, col2, col3 = st.columns(3)
        col1.metric("Total scraped", total)
        col2.metric("Passed keyword filter", kept, delta=f"-{rejected} removed")
        col3.metric("Will be sent to Claude", kept)

        if kept == 0:
            st.warning("⚠️ No listings passed the keyword filter. Try broadening your keywords or check that listing descriptions were scraped correctly.")
        else:
            # Show survivors
            preview = []
            for l in survivors[:15]:
                matched = l.get("_matched_keywords", [])
                preview.append({
                    "Address": l.get("address", "—"),
                    "Price": f"£{l.get('price', 0):,}" if l.get("price") else "—",
                    "Matched keywords": ", ".join(matched) if matched else "—",
                    "Description snippet": l.get("description", "")[:120] + "..." if l.get("description") else "—",
                })
            st.markdown(f"**Listings passing filter (showing up to 15 of {kept}):**")
            st.dataframe(preview, use_container_width=True)

            if st.session_state.step == 3:
                st.markdown('<div class="warning-box">👆 Review the listings above. Do they look like genuine land/acreage properties? You can adjust keywords and re-run, or proceed to Claude analysis.</div>', unsafe_allow_html=True)
                col1, col2 = st.columns([1, 3])
                with col1:
                    if st.button("✅ Confirmed — send to Claude →", type="primary"):
                        st.session_state.step = 4
                        st.rerun()
                with col2:
                    if st.button("🔄 Adjust keywords and re-filter"):
                        st.session_state.keyword_survivors = None
                        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════════
# STEP 4 — CLAUDE ANALYSIS
# ═════════════════════════════════════════════════════════════════════════════
if st.session_state.step >= 4:
    step4_class = "step-box step-complete" if st.session_state.step > 4 else "step-box"
    st.markdown(f'<div class="{step4_class}">', unsafe_allow_html=True)
    st.subheader("Step 4 — Claude analysis")
    st.markdown(f"""
    Claude will read each of the **{len(st.session_state.keyword_survivors or [])} surviving listings** 
    and extract: land size, key land features, renovation status, and a brief summary.
    """)

    if st.session_state.step == 4 and st.session_state.claude_results is None:
        survivors = st.session_state.keyword_survivors or []
        estimated_cost = len(survivors) * 0.004  # rough pence estimate
        st.info(f"💰 Estimated Claude API cost for this batch: ~£{estimated_cost:.2f}")

        if st.button("🤖 Run Claude analysis", type="primary"):
            results = []
            progress = st.progress(0, text="Analysing listings with Claude...")
            for i, listing in enumerate(survivors):
                result = run_claude_analysis(listing)
                results.append(result)
                progress.progress((i + 1) / len(survivors), text=f"Analysed {i+1} of {len(survivors)} listings...")
                time.sleep(0.1)  # avoid rate limiting
            progress.empty()
            st.session_state.claude_results = results
            st.rerun()

    if st.session_state.claude_results is not None:
        results = st.session_state.claude_results
        st.success(f"✅ Claude analysis complete — {len(results)} listings analysed")

        # Build display table
        display = []
        for r in results:
            display.append({
                "Address": r.get("address", "—"),
                "Price": f"£{r.get('price', 0):,}" if r.get("price") else "—",
                "Land size": r.get("land_size", "Not specified"),
                "Land type": r.get("land_type", "—"),
                "Renovation needed": r.get("renovation_needed", "Unknown"),
                "Summary": r.get("summary", "—"),
                "Rightmove link": r.get("url", "—"),
            })

        st.dataframe(display, use_container_width=True)

        if st.session_state.step == 4:
            st.markdown('<div class="warning-box">👆 Review Claude\'s land size extractions above. Do they look accurate? You can proceed to commute checking, or go back and adjust filters.</div>', unsafe_allow_html=True)

            # Optional: filter by confirmed land size before commute check
            min_acres_confirm = st.number_input(
                "Only proceed with properties where land size is at least (acres) — enter 0 to keep all:",
                min_value=0.0, max_value=50.0, value=1.0, step=0.5,
            )

            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("✅ Confirmed — check commute times →", type="primary"):
                    if min_acres_confirm > 0:
                        # Filter to only those with confirmed acreage
                        filtered = []
                        for r in results:
                            acres = r.get("land_size_acres")
                            if acres is not None and acres >= min_acres_confirm:
                                filtered.append(r)
                            elif acres is None and r.get("land_size") not in [None, "Not specified", "Unknown"]:
                                # Claude found land mention but couldn't parse number — keep them
                                filtered.append(r)
                        st.session_state.claude_results = filtered
                    st.session_state.step = 5
                    st.rerun()
            with col2:
                if st.button("🔄 Re-run Claude analysis"):
                    st.session_state.claude_results = None
                    st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════════
# STEP 5 — COMMUTE CHECK
# ═════════════════════════════════════════════════════════════════════════════
if st.session_state.step >= 5:
    step5_class = "step-box step-complete" if st.session_state.commute_results is not None else "step-box"
    st.markdown(f'<div class="{step5_class}">', unsafe_allow_html=True)
    st.subheader("Step 5 — Commute time check")
    st.markdown(f"""
    Google Maps will calculate public transport commute times from each property to Bristol Temple Meads 
    and London Paddington. Running for **{len(st.session_state.claude_results or [])} properties**.
    """)

    # Sliders always active — changing them re-filters existing results instantly,
    # or sets parameters for the next run
    col1, col2 = st.columns(2)
    with col1:
        max_bristol = st.slider("Max commute to Bristol (mins)", 30, 180, 90, 5)
    with col2:
        max_london = st.slider("Max commute to London (mins)", 30, 180, 100, 5)

    # ── Run commute check (first time, or re-run) ─────────────────────────────
    if st.session_state.commute_results is None:
        properties = st.session_state.claude_results or []
        estimated_cost = len(properties) * 2 * 0.001
        st.info(f"💰 Estimated Google Maps API cost: ~£{estimated_cost:.3f} ({len(properties) * 2} lookups)")

        if st.button("🗺️ Check commute times", type="primary"):
            checked = []
            progress = st.progress(0, text="Checking commute times...")
            for i, listing in enumerate(properties):
                result = run_commute_check(listing)
                checked.append(result)
                progress.progress((i + 1) / len(properties), text=f"Checked {i+1} of {len(properties)} properties...")
            progress.empty()
            st.session_state.commute_results = checked
            st.session_state.final_results = checked  # keep for backwards compat
            st.rerun()

    # ── Results display ───────────────────────────────────────────────────────
    if st.session_state.commute_results is not None:
        all_results = st.session_state.commute_results

        # Filter is applied live — no re-run needed just to change thresholds
        filtered_final = [
            r for r in all_results
            if (r.get("commute_bristol_mins") or 999) <= max_bristol
            and (r.get("commute_london_mins") or 999) <= max_london
        ]

        st.success(
            f"✅ {len(filtered_final)} properties match your commute limits "
            f"(of {len(all_results)} checked) — adjust sliders above to update instantly"
        )

        if filtered_final:
            display = []
            for r in filtered_final:
                bristol = r.get("commute_bristol_mins")
                london = r.get("commute_london_mins")
                display.append({
                    "Address": r.get("address", "—"),
                    "Price": f"£{r.get('price', 0):,}" if r.get("price") else "—",
                    "Land size": r.get("land_size", "—"),
                    "Land type": r.get("land_type", "—"),
                    "→ Bristol (mins)": f"{bristol}" if bristol else "N/A",
                    "→ London (mins)": f"{london}" if london else "N/A",
                    "Renovation": r.get("renovation_needed", "—"),
                    "Schools": r.get("top_school_rating", "—"),
                    "Link": r.get("url", "—"),
                })

            st.markdown("### 🏡 Your shortlist")
            st.dataframe(display, use_container_width=True, height=400)

            import pandas as pd
            df = pd.DataFrame(display)
            csv = df.to_csv(index=False)
            st.download_button(
                label="⬇️ Download shortlist as CSV",
                data=csv,
                file_name="property_shortlist.csv",
                mime="text/csv",
            )

            st.markdown("### Property details")
            for r in filtered_final:
                with st.expander(f"🏠 {r.get('address', 'Unknown')} — £{r.get('price', 0):,}"):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Land size", r.get("land_size", "—"))
                    col2.metric("Bristol commute", f"{r.get('commute_bristol_mins', '—')} mins")
                    col3.metric("London commute", f"{r.get('commute_london_mins', '—')} mins")
                    st.markdown(f"**Claude's summary:** {r.get('summary', '—')}")
                    if r.get("url"):
                        st.markdown(f"[View on Rightmove →]({r['url']})")
        else:
            st.warning("No properties matched your commute time limits. Try increasing the sliders above — no re-run needed.")

        # ── Bottom controls ───────────────────────────────────────────────────
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Re-run commute check", help="Re-fetches commute times from Google Maps. Use if you want to check a different departure time or if results look wrong. Steps 1–4 are preserved."):
                st.session_state.commute_results = None
                st.session_state.final_results = None
                st.rerun()
        with col2:
            if st.button("🔁 Start a new search", help="Clears everything and starts from Step 1."):
                for k in defaults:
                    st.session_state[k] = defaults[k]
                st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)
