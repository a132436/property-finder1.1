# 🏡 Property Finder

A Streamlit app that searches Rightmove for properties with land, filtering by acreage, commute time to Bristol and London, and school quality.

## How it works

1. **Paste a Rightmove search URL** — set your price, area and property type filters on Rightmove first
2. **Apify scrapes the listings** — retrieves full details including description text
3. **Keyword filter** — free text scan keeps only listings mentioning land/acres/paddock etc.
4. **Claude analyses survivors** — extracts precise land size, land type and renovation status
5. **Google Maps commute check** — calculates public transport time to Bristol and London

At each step you review the results and manually confirm before proceeding.

## Setup

### 1. Clone this repository
```bash
git clone https://github.com/YOUR_USERNAME/property-finder.git
```

### 2. Deploy to Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click **New app**
3. Connect your GitHub account and select this repository
4. Set **Main file path** to `app.py`
5. Click **Deploy**

### 3. Add your API keys

In your deployed app, go to **⋮ Menu → Settings → Secrets** and paste:

```toml
APIFY_API_TOKEN = "apify_api_your_token_here"
ANTHROPIC_API_KEY = "sk-ant-your_key_here"
GOOGLE_MAPS_API_KEY = "your_google_maps_key_here"
```

You'll find each key at:
- **Apify**: console.apify.com → Settings → Integrations
- **Anthropic**: console.anthropic.com → API Keys
- **Google Maps**: console.cloud.google.com → APIs & Services → Credentials

### 4. Use the app

Go to your Streamlit app URL, paste a Rightmove search URL, and follow the steps.

## Estimated costs per search run

| Service | Cost for 100 listings |
|---------|----------------------|
| Apify scrape | ~$0.04 (well within free tier) |
| Claude analysis | ~£0.05–0.10 (only for keyword survivors) |
| Google Maps | ~£0.001–0.01 (only for Claude survivors) |

## Tips for best results

- Set your price range and property type filters on Rightmove before copying the URL
- Use Rightmove's "Draw a search" tool to define a geographic area
- Sort by "Newest listed" to catch new properties first
- The keyword filter works best when listings include descriptions — some agents provide very thin listings
