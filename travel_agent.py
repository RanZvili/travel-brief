#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║      SAPIENS SALES TRAVEL BRIEF AGENT                       ║
║      Powered by Gemini AI + Open-Meteo Weather API          ║
╚══════════════════════════════════════════════════════════════╝

What this does:
  Give it an origin city, destination city/country, and travel dates.
  It calls Claude AI (which calls real weather and timezone APIs),
  then generates a beautiful HTML travel brief + PDF for your trip.

What you get:
  • Weather forecast (real data, day by day)
  • Time difference with home
  • Power outlet type + adapter needed?
  • Dress code for insurance/finance executives in that country
  • Ride-hailing apps available there
  • 5 mid-range restaurant recommendations
  • Currency & tipping customs
  • Public holidays during your trip
  • Business meeting etiquette
  • Top 5 attractions for a free evening
  • Airport → city center transfer info

SETUP (one time):
  1. Install Python 3.9+ from https://python.org
  2. Open Terminal (Mac/Linux) or Command Prompt (Windows)
  3. Run:  pip install google-generativeai requests
  4. Get a free API key at https://aistudio.google.com/app/apikey
  5. Set it:
       Mac/Linux:  export GEMINI_API_KEY=AIza...
       Windows:    set GEMINI_API_KEY=AIza...

USAGE:
  Interactive mode (recommended):
    python travel_agent.py

  Or pass all arguments at once:
    python travel_agent.py "Tel Aviv" "London" "United Kingdom" "2026-09-10" "2026-09-13"

OUTPUT:
  Two files saved in the same folder as this script:
    travel_brief_london_2026-09-10.html   ← open in any browser
    travel_brief_london_2026-09-10.pdf    ← requires weasyprint
                                              (pip install weasyprint)
  If PDF generation fails, open the HTML and use File → Print → Save as PDF
"""

# google-genai SDK removed — using direct REST API for reliability
import requests
import json
import os
import sys
from datetime import datetime
from pathlib import Path


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: WEATHER CODE LABELS
# WMO (World Meteorological Organization) standard codes returned by Open-Meteo
# ══════════════════════════════════════════════════════════════════════════════

WMO_CODES = {
    0: "Clear sky",        1: "Mainly clear",     2: "Partly cloudy",    3: "Overcast",
    45: "Foggy",           48: "Icy fog",
    51: "Light drizzle",   53: "Drizzle",          55: "Dense drizzle",
    61: "Slight rain",     63: "Moderate rain",    65: "Heavy rain",
    71: "Slight snow",     73: "Moderate snow",    75: "Heavy snow",
    80: "Light showers",   81: "Showers",          82: "Heavy showers",
    95: "Thunderstorm",    96: "Thunderstorm+hail", 99: "Heavy thunderstorm"
}


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: TOOL DEFINITIONS
# These describe the tools Claude can call. The actual code is in Section 3.
# ══════════════════════════════════════════════════════════════════════════════

GEMINI_TOOLS = {
    "function_declarations": [
        {
            "name": "get_weather_forecast",
            "description": (
                "Fetch a real daily weather forecast for a city over a date range. "
                "Returns max/min temperature (C), precipitation (mm), wind speed (km/h), "
                "and a human-readable weather condition per day."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city":       {"type": "string", "description": "City name, e.g. 'London'"},
                    "country":    {"type": "string", "description": "Country name, e.g. 'United Kingdom'"},
                    "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                    "end_date":   {"type": "string", "description": "End date in YYYY-MM-DD format"},
                },
                "required": ["city", "country", "start_date", "end_date"]
            }
        },
        {
            "name": "get_timezone_info",
            "description": (
                "Get the IANA timezone name and current UTC offset (hours) for a city. "
                "IMPORTANT: Call this for BOTH the origin AND destination city."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city":    {"type": "string", "description": "City name"},
                    "country": {"type": "string", "description": "Country name"},
                },
                "required": ["city", "country"]
            }
        }
    ]
}


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: TOOL IMPLEMENTATIONS
# Real Python functions that fetch data from free APIs
# ══════════════════════════════════════════════════════════════════════════════

def get_weather_forecast(city: str, country: str, start_date: str, end_date: str) -> dict:
    """
    Calls Open-Meteo (open-meteo.com) — free, no API key, high accuracy.
    Step 1: Geocode the city name to latitude/longitude
    Step 2: Fetch forecast for those coordinates
    """
    try:
        # Step 1: Find the city coordinates
        geo_response = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 5, "language": "en"},
            timeout=10
        ).json()

        if not geo_response.get("results"):
            return {"error": f"City not found: {city}, {country}"}

        # Pick the result that best matches the country
        location = geo_response["results"][0]
        for result in geo_response["results"]:
            if country.lower() in result.get("country", "").lower():
                location = result
                break

        # Step 2: Fetch the weather forecast
        weather_response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude":  location["latitude"],
                "longitude": location["longitude"],
                "daily": ",".join([
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_sum",
                    "weathercode",
                    "windspeed_10m_max"
                ]),
                "start_date":      start_date,
                "end_date":        end_date,
                "timezone":        location.get("timezone", "UTC"),
                "wind_speed_unit": "kmh",
            },
            timeout=10
        ).json()

        daily = weather_response.get("daily", {})
        forecast_days = []
        for i, date_str in enumerate(daily.get("time", [])):
            forecast_days.append({
                "date":      date_str,
                "max_c":     round(daily["temperature_2m_max"][i], 1),
                "min_c":     round(daily["temperature_2m_min"][i], 1),
                "rain_mm":   round(daily["precipitation_sum"][i], 1),
                "condition": WMO_CODES.get(daily.get("weathercode", [0] * 20)[i], "Unknown"),
                "wind_kmh":  round(daily.get("windspeed_10m_max", [0] * 20)[i], 1),
            })

        return {
            "city":     location["name"],
            "country":  location.get("country", country),
            "timezone": location.get("timezone", "UTC"),
            "forecast": forecast_days
        }

    except Exception as e:
        return {"error": f"Weather API error: {str(e)}"}


def get_timezone_info(city: str, country: str) -> dict:
    """
    Geocodes the city via Open-Meteo to get its IANA timezone name,
    then uses Python's zoneinfo to find the current UTC offset.
    """
    try:
        geo_response = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 5, "language": "en"},
            timeout=10
        ).json()

        if not geo_response.get("results"):
            return {"error": f"City not found: {city}, {country}"}

        location = geo_response["results"][0]
        for result in geo_response["results"]:
            if country.lower() in result.get("country", "").lower():
                location = result
                break

        timezone_name = location.get("timezone", "UTC")
        utc_offset_hours = None
        current_local_time = None

        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(timezone_name)
            now = datetime.now(tz)
            utc_offset_hours = round(now.utcoffset().total_seconds() / 3600, 1)
            current_local_time = now.strftime("%H:%M")
        except Exception:
            pass

        return {
            "city":              location["name"],
            "country":           location.get("country", country),
            "timezone":          timezone_name,
            "utc_offset_hours":  utc_offset_hours,
            "current_local_time": current_local_time
        }

    except Exception as e:
        return {"error": f"Timezone lookup error: {str(e)}"}


def dispatch_tool(tool_name: str, tool_inputs: dict) -> str:
    """Routes a tool call from Claude to the right Python function."""
    if tool_name == "get_weather_forecast":
        result = get_weather_forecast(**tool_inputs)
    elif tool_name == "get_timezone_info":
        result = get_timezone_info(**tool_inputs)
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    return json.dumps(result, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4: SYSTEM PROMPT
# This is the instruction set given to Claude. It tells Claude what to do,
# which tools to use, and exactly what JSON format to return.
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are a travel preparation assistant for sales representatives at Sapiens, \
an enterprise insurance software company headquartered in Israel. \
Your reps fly frequently to meet insurance company executives around the world.

Your job: given an origin, destination, and travel dates — produce a comprehensive travel brief \
that makes the rep feel prepared, professional, and confident from the moment they land.

━━━ TOOLS ━━━
You have two real-time tools:
1. get_weather_forecast — call for DESTINATION to get actual day-by-day forecast data
2. get_timezone_info — call for BOTH origin AND destination to compute the exact time difference

━━━ KNOWLEDGE SECTIONS (answer from your own knowledge) ━━━

outlet_type:
  - The power plug/outlet type(s) used in the destination country (use letter codes: A, B, C, D, E, F, G, H, I, K, L, M, N)
  - Voltage and frequency (e.g. 230V/50Hz)
  - Whether an Israeli traveler (Type H, 230V) needs an adapter and/or voltage converter

dress_code:
  - What do C-suite and senior management in insurance/financial services companies wear in that country?
  - Be specific: formal suit? Business casual? Any regional nuances (e.g. conservative colors in Asia)?

transport_apps:
  - Which ride-hailing or taxi apps are most used in that city
  - Note if Uber works there or if a local alternative is better (Bolt, Gett, Grab, Ola, DiDi, Careem, etc.)

restaurants:
  - 5 real, well-reviewed, mid-range restaurants in the destination city
  - Good for a business dinner or relaxed meal after a long day
  - Each: name, cuisine type, estimated cost per person in USD, approximate latitude/longitude coordinates, and why it's good
  - Avoid tourist traps. Prefer places that feel local and genuine.

currency:
  - Local currency name, symbol, ISO code
  - Exchange rate vs USD (approximate is fine)
  - Exchange rate from the ORIGIN city's local currency to the destination currency (e.g. if origin is Tel Aviv, show ILS → destination currency rate)
  - Include origin_currency_code (e.g. "ILS"), origin_currency_symbol (e.g. "₪"), and origin_rate (e.g. "1 ₪ ≈ 2.85 SEK")
  - Whether international credit cards (Visa/Mastercard) are widely accepted
  - Local tipping culture (percentage? not expected? rounding up?)

public_holidays:
  - Any public holidays in the destination country that fall within the travel dates
  - Flag if this could affect business meetings (offices closed, etc.)
  - If none, explicitly say so

business_etiquette:
  - 4-6 cultural norms that matter when meeting insurance/financial executives in that country
  - Cover: punctuality, greeting style, business card customs (if relevant), formality level,
    topics to avoid, anything that makes a strong first impression

attractions:
  - Top 5 things to see or do for someone with a free evening or morning
  - Keep it practical — walkable from city center or easy by public transit
  - Each: name, type, approximate latitude/longitude coordinates, and why it's worth seeing

airport_transfer:
  - Best way from the main international airport to city center
  - Include: airport_name (full name of the main international airport, e.g. "Arlanda Airport"),
    mode of transport (metro, train, taxi, bus), estimated time, approximate cost
    in both local currency and USD

company_addresses:
  - If a company_name is provided, list up to 3 known office addresses for that company
    in the destination city. Each: name (branch/office name), address (full street address),
    maps_query (the best Google Maps search string to find it).
  - If no company_name is given or no addresses are known, return an empty array.

company_addresses:
  - If company_name is provided, list up to 3 known office addresses for that company in
    the destination city. Each entry: name (branch name), address (full street address),
    maps_query (best Google Maps search string). If unknown or not provided, return [].

━━━ OUTPUT FORMAT ━━━
Return ONLY a single valid JSON object. No markdown fences, no explanatory prose, just JSON.

{
  "destination": "City, Country",
  "origin": "City, Country",
  "travel_dates": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
  "time_difference": {
    "origin_tz": "Asia/Jerusalem",
    "destination_tz": "Europe/London",
    "difference_hours": -2,
    "summary": "London is 2 hours behind Tel Aviv"
  },
  "weather_forecast": [
    {"date": "2026-09-10", "max_c": 20, "min_c": 13, "rain_mm": 1.2, "condition": "Partly cloudy", "wind_kmh": 18}
  ],
  "outlet_type": {
    "types": ["G"],
    "voltage": "230V/50Hz",
    "adapter_needed": true,
    "notes": "Type G uses three rectangular pins. Israeli Type H plug won't fit — bring a universal adapter."
  },
  "dress_code": "Full business formal is standard in UK insurance/finance. Dark suit (navy or charcoal), white or light-blue shirt, tie. Women: formal suit or smart dress. First meetings especially should be conservative.",
  "transport_apps": [
    {"name": "Uber", "notes": "works well throughout London"},
    {"name": "Bolt", "notes": "often cheaper than Uber"},
    {"name": "Black Cab (Gett)", "notes": "official London black cabs, reliable and metered"}
  ],
  "restaurants": [
    {"name": "Brasserie Zédel", "cuisine": "French brasserie", "price_usd": "25-35", "lat": 51.5098, "lon": -0.1344, "notes": "Stunning Art Deco dining room in Piccadilly, excellent value, great for impressing guests without overspending."},
    {"name": "Dishoom", "cuisine": "Indian", "price_usd": "20-30", "lat": 51.5133, "lon": -0.1245, "notes": "Consistently excellent, Bombay café atmosphere, popular with London professionals. Book ahead."},
    {"name": "Flat Iron", "cuisine": "Steakhouse", "price_usd": "20-28", "lat": 51.5115, "lon": -0.1307, "notes": "No-frills but excellent quality steaks. Great for a relaxed post-meeting dinner."}
  ],
  "currency": {
    "name": "British Pound Sterling",
    "symbol": "£",
    "code": "GBP",
    "approx_usd_rate": "1 GBP ≈ 1.27 USD",
    "origin_currency_code": "ILS",
    "origin_currency_symbol": "₪",
    "origin_rate": "1 ₪ ≈ 0.22 GBP",
    "cards_accepted": "Cards accepted almost everywhere, contactless preferred",
    "tipping": "10-15% in restaurants if service charge not already included; round up for taxis"
  },
  "public_holidays": [],
  "business_etiquette": "Punctuality is crucial — being even 5 minutes late is noticed. Greet with a firm handshake and eye contact. Business cards are exchanged but without ceremony. Understatement is valued: avoid boasting about your company or product. Small talk before business is normal (weather, sports). Avoid discussing salary, politics, or religion. Thank-you emails after meetings are appreciated.",
  "attractions": [
    {"name": "Tower of London & Tower Bridge", "type": "Historic landmark", "lat": 51.5081, "lon": -0.0759, "notes": "15 min walk from the City financial district. Iconic and worth seeing at dusk."},
    {"name": "Tate Modern", "type": "Art museum", "lat": 51.5076, "lon": -0.0994, "notes": "Free entry, world-class modern art, great café with Thames views. Perfect for 2 hours."},
    {"name": "Borough Market", "type": "Food market", "lat": 51.5055, "lon": -0.0910, "notes": "Best food market in London, open Thursdays–Saturdays. Perfect for a quick lunch or to bring back local gifts."}
  ],
  "airport_transfer": {
    "airport_name": "Heathrow Airport",
    "recommended": "Heathrow Express train to Paddington",
    "time_mins": 15,
    "cost_local": "£25-32",
    "cost_usd": "32-41"
  }
}"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5: AGENT — pre-fetch data, then single Gemini call
# ══════════════════════════════════════════════════════════════════════════════

def run_agent(origin: str, destination_city: str, destination_country: str,
              start_date: str, end_date: str, company_name: str = "") -> dict:
    """
    1. Pre-fetch weather + timezone data directly (no Gemini needed for this)
    2. Send everything to Gemini in ONE message → it returns the full JSON brief
    This avoids multiple round-trips and rate-limit issues.
    """
    import re, time as _time

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")

    # ── Step 1: pre-fetch real data ──────────────────────────────────────────
    print(f"\n🌍  Pre-fetching data for {destination_city}, {destination_country}...")

    origin_country  = origin.split(",")[-1].strip() if "," in origin else ""
    origin_city     = origin.split(",")[0].strip()

    weather_data  = get_weather_forecast(destination_city, destination_country, start_date, end_date)
    tz_dest       = get_timezone_info(destination_city, destination_country)
    tz_origin     = get_timezone_info(origin_city, origin_country or origin)

    print("    ✅  Weather and timezone data fetched")

    # ── Step 2: single Gemini call (direct REST — no SDK, real timeout) ────────
    message = (
        f"Create a complete travel brief. Here is the pre-fetched real-time data:\n\n"
        f"TRIP:\n"
        f"  Origin:      {origin}\n"
        f"  Destination: {destination_city}, {destination_country}\n"
        f"  Dates:       {start_date} to {end_date}\n"
        + (f"  Company:     {company_name}\n" if company_name else "")
        + f"\nWEATHER FORECAST (real data):\n{json.dumps(weather_data, indent=2)}\n"
        f"\nDESTINATION TIMEZONE (real data):\n{json.dumps(tz_dest, indent=2)}\n"
        f"\nORIGIN TIMEZONE (real data):\n{json.dumps(tz_origin, indent=2)}\n"
        f"\nUsing the above real data plus your own knowledge, return the complete JSON travel brief now. "
        f"Do NOT call any tools — all real-time data is already provided above."
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={api_key}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": message}]}],
        "generationConfig": {
            "temperature": 0.1,
            "thinkingConfig": {"thinkingBudget": 0},  # disable thinking → fast
        },
    }

    response_text = None
    for attempt in range(6):
        try:
            resp = requests.post(url, json=payload, timeout=90)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 30 * (attempt + 1)))
                print(f"    ⏳  Rate limited. Waiting {retry_after}s (attempt {attempt+1}/6)...")
                _time.sleep(retry_after)
                if attempt == 5:
                    raise RuntimeError(f"Rate limited after 6 attempts: {resp.text}")
                continue
            resp.raise_for_status()
            data = resp.json()
            response_text = data["candidates"][0]["content"]["parts"][0]["text"]
            break
        except requests.exceptions.Timeout:
            print(f"    ⏳  Request timed out (attempt {attempt+1}/6), retrying...")
            if attempt == 5:
                raise RuntimeError("Gemini API timed out after 6 attempts.")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Gemini API error: {e}")

    # ── Step 3: parse JSON from response ────────────────────────────────────
    text = response_text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:].strip()
    start_idx = text.find("{")
    end_idx   = text.rfind("}") + 1
    if start_idx >= 0 and end_idx > start_idx:
        return json.loads(text[start_idx:end_idx])
    raise ValueError(f"No JSON found in Gemini response. Raw: {text[:300]}")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 & 7: OUTLET SVG ICONS + HTML DASHBOARD GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

OUTLET_SVGS = {
    "A": '<svg viewBox="0 0 60 60" width="48" height="48"><rect x="2" y="2" width="56" height="56" rx="10" fill="rgba(255,255,255,0.15)" stroke="rgba(255,255,255,0.3)" stroke-width="1.5"/><rect x="20" y="13" width="8" height="24" rx="3" fill="rgba(255,255,255,0.9)"/><rect x="32" y="13" width="8" height="24" rx="3" fill="rgba(255,255,255,0.9)"/></svg>',
    "B": '<svg viewBox="0 0 60 60" width="48" height="48"><rect x="2" y="2" width="56" height="56" rx="10" fill="rgba(255,255,255,0.15)" stroke="rgba(255,255,255,0.3)" stroke-width="1.5"/><rect x="20" y="11" width="8" height="22" rx="3" fill="rgba(255,255,255,0.9)"/><rect x="32" y="11" width="8" height="22" rx="3" fill="rgba(255,255,255,0.9)"/><circle cx="30" cy="43" r="5.5" fill="rgba(255,255,255,0.9)"/></svg>',
    "C": '<svg viewBox="0 0 60 60" width="48" height="48"><rect x="2" y="2" width="56" height="56" rx="10" fill="rgba(255,255,255,0.15)" stroke="rgba(255,255,255,0.3)" stroke-width="1.5"/><circle cx="20" cy="30" r="7" fill="rgba(255,255,255,0.9)"/><circle cx="40" cy="30" r="7" fill="rgba(255,255,255,0.9)"/></svg>',
    "D": '<svg viewBox="0 0 60 60" width="48" height="48"><rect x="2" y="2" width="56" height="56" rx="10" fill="rgba(255,255,255,0.15)" stroke="rgba(255,255,255,0.3)" stroke-width="1.5"/><circle cx="30" cy="16" r="7" fill="rgba(255,255,255,0.9)"/><circle cx="17" cy="42" r="7" fill="rgba(255,255,255,0.9)"/><circle cx="43" cy="42" r="7" fill="rgba(255,255,255,0.9)"/></svg>',
    "F": '<svg viewBox="0 0 60 60" width="48" height="48"><rect x="2" y="2" width="56" height="56" rx="10" fill="rgba(255,255,255,0.15)" stroke="rgba(255,255,255,0.3)" stroke-width="1.5"/><circle cx="20" cy="26" r="7" fill="rgba(255,255,255,0.9)"/><circle cx="40" cy="26" r="7" fill="rgba(255,255,255,0.9)"/><rect x="4" y="40" width="10" height="7" rx="2" fill="rgba(255,255,255,0.6)"/><rect x="46" y="40" width="10" height="7" rx="2" fill="rgba(255,255,255,0.6)"/></svg>',
    "G": '<svg viewBox="0 0 60 60" width="48" height="48"><rect x="2" y="2" width="56" height="56" rx="10" fill="rgba(255,255,255,0.15)" stroke="rgba(255,255,255,0.3)" stroke-width="1.5"/><rect x="12" y="13" width="13" height="17" rx="3" fill="rgba(255,255,255,0.9)"/><rect x="35" y="13" width="13" height="17" rx="3" fill="rgba(255,255,255,0.9)"/><rect x="20" y="36" width="20" height="13" rx="3" fill="rgba(255,255,255,0.9)"/></svg>',
    "H": '<svg viewBox="0 0 60 60" width="48" height="48"><rect x="2" y="2" width="56" height="56" rx="10" fill="rgba(255,255,255,0.15)" stroke="rgba(255,255,255,0.3)" stroke-width="1.5"/><rect x="26" y="9" width="8" height="19" rx="3" fill="rgba(255,255,255,0.9)"/><rect x="8" y="33" width="8" height="19" rx="3" fill="rgba(255,255,255,0.9)" transform="rotate(30 12 42)"/><rect x="44" y="33" width="8" height="19" rx="3" fill="rgba(255,255,255,0.9)" transform="rotate(-30 48 42)"/></svg>',
    "I": '<svg viewBox="0 0 60 60" width="48" height="48"><rect x="2" y="2" width="56" height="56" rx="10" fill="rgba(255,255,255,0.15)" stroke="rgba(255,255,255,0.3)" stroke-width="1.5"/><rect x="18" y="14" width="8" height="20" rx="3" fill="rgba(255,255,255,0.9)" transform="rotate(-35 22 24)"/><rect x="34" y="14" width="8" height="20" rx="3" fill="rgba(255,255,255,0.9)" transform="rotate(35 38 24)"/><circle cx="30" cy="46" r="5" fill="rgba(255,255,255,0.9)"/></svg>',
    "M": '<svg viewBox="0 0 60 60" width="48" height="48"><rect x="2" y="2" width="56" height="56" rx="10" fill="rgba(255,255,255,0.15)" stroke="rgba(255,255,255,0.3)" stroke-width="1.5"/><circle cx="30" cy="15" r="8" fill="rgba(255,255,255,0.9)"/><circle cx="15" cy="43" r="8" fill="rgba(255,255,255,0.9)"/><circle cx="45" cy="43" r="8" fill="rgba(255,255,255,0.9)"/></svg>',
    "N": '<svg viewBox="0 0 60 60" width="48" height="48"><rect x="2" y="2" width="56" height="56" rx="10" fill="rgba(255,255,255,0.15)" stroke="rgba(255,255,255,0.3)" stroke-width="1.5"/><circle cx="20" cy="24" r="7" fill="rgba(255,255,255,0.9)"/><circle cx="40" cy="24" r="7" fill="rgba(255,255,255,0.9)"/><circle cx="30" cy="43" r="7" fill="rgba(255,255,255,0.9)"/></svg>',
}

WX_EMOJI = {"clear":"☀️","mainly clear":"🌤","partly":"⛅","overcast":"☁️","fog":"🌫","drizzle":"🌦","rain":"🌧","snow":"❄️","shower":"🌦","thunder":"⛈"}

def wx_emoji(c):
    cl = c.lower()
    for k,v in WX_EMOJI.items():
        if k in cl: return v
    return "🌡"



WX_DATA = {
    "clear":        ("☀️","#ff9a3c","#7c3800"),
    "mainly clear": ("🌤","#ffb347","#7c4200"),
    "partly":       ("⛅","#74b9ff","#1a4a80"),
    "overcast":     ("☁️","#a29bfe","#3d2fa0"),
    "fog":          ("🌫","#b2bec3","#2d3436"),
    "drizzle":      ("🌦","#55efc4","#006651"),
    "rain":         ("🌧","#74b9ff","#003580"),
    "shower":       ("🌦","#74b9ff","#003580"),
    "snow":         ("❄️","#dfe6e9","#2d3436"),
    "thunder":      ("⛈","#fd79a8","#6d0035"),
}

def wx(cond):
    c = cond.lower()
    for k, v in WX_DATA.items():
        if k in c: return v
    return ("🌡","#636e72","#dfe6e9")


def generate_html(data: dict) -> str:
    dest   = data["destination"]
    origin = data["origin"]
    dates  = data["travel_dates"]
    start, end = dates["start"], dates["end"]
    try:
        s = datetime.strptime(start, "%Y-%m-%d")
        e = datetime.strptime(end,   "%Y-%m-%d")
        dfmt   = f"{s.strftime('%b %d')} – {e.strftime('%b %d, %Y')}"
        nights = (e - s).days
        nstr   = f"{nights} night{'s' if nights != 1 else ''}"
    except:
        dfmt = f"{start} – {end}"; nstr = ""

    td = data.get("time_difference", {})
    try:
        dh = float(td.get("difference_hours", 0))
        da = abs(dh); di = int(da)
        dstr = f"{di}h{'30m' if da - di >= 0.5 else ''} {'ahead' if dh > 0 else 'behind'}"
    except:
        dstr = str(td.get("difference_hours", ""))

    outlet  = data.get("outlet_type", {})
    otypes  = outlet.get("types", ["C"])
    adapter = outlet.get("adapter_needed", True)
    outlet_html = "".join(
        f'<div class="plug"><div class="plug-svg">{OUTLET_SVGS.get(t.upper(), OUTLET_SVGS["C"])}</div><div class="plug-label">Type {t}</div></div>'
        for t in otypes
    )

    cur   = data.get("currency", {})
    rests = data.get("restaurants", [])
    attr  = data.get("attractions", [])
    trans = data.get("transport_apps", [])
    hols  = data.get("public_holidays", [])
    apt   = data.get("airport_transfer", {})
    cos   = data.get("company_addresses", [])
    dress = data.get("dress_code", "")
    etiq  = data.get("business_etiquette", "")

    # Weather cards
    wx_cards = ""
    for d in data.get("weather_forecast", []):
        try: dl = datetime.strptime(d["date"], "%Y-%m-%d").strftime("%a %-d")
        except: dl = d["date"]
        em, bg, fg = wx(d.get("condition", ""))
        rain = d.get("rain_mm", 0)
        wx_cards += (
            f'<div class="wc" style="background:{bg};color:{fg}">'
            f'<div class="wc-em">{em}</div>'
            f'<div class="wc-body">'
            f'<div class="wc-day">{dl}</div>'
            f'<div class="wc-temps">{d.get("max_c","?")}° <span class="wc-lo">{d.get("min_c","?")}°</span></div>'
            f'<div class="wc-cond">{d.get("condition","")}</div>'
            + (f'<div class="wc-rain">🌧 {rain}mm</div>' if rain > 0.5 else '')
            + f'</div></div>'
        )

    # POI rows — name + purple meta always visible, gray note collapsible
    poi_counter = [0]
    def poi_rows(items, dest_name):
        h = ""
        for i, x in enumerate(items, 1):
            poi_counter[0] += 1
            pid  = f"poi{poi_counter[0]}"
            nm   = x.get("name", "")
            meta = x.get("cuisine") or x.get("type", "")
            price = f" · ~${x.get('price_usd','')}/pp" if x.get("price_usd") else ""
            note = x.get("notes", "")
            lat  = x.get("lat", "")
            lon  = x.get("lon", "")
            lat_attrs = f' data-lat="{lat}" data-lon="{lon}"' if lat and lon else ""
            h += (
                f'<div class="poi">'
                f'  <div class="poi-top">'
                f'    <div style="flex:1;min-width:0">'
                f'      <div class="poi-title-row">'
                f'        <span class="poi-n">{i}</span>'
                f'        <span class="poi-title">{nm}</span>'
                f'      </div>'
                f'      <div class="poi-meta">{meta}{price}'
                + (f' <button class="expand-btn" onclick="toggleNote(\'{pid}\')" id="btn-{pid}">▾ more</button>' if note else '')
                + f'</div>'
                f'    </div>'
                f'    <button class="walk-btn" id="wb-{pid}" onclick="walkTo(\'{nm}, {dest_name}\')" {lat_attrs}>🗺</button>'
                f'  </div>'
                + (f'  <div class="poi-note" id="{pid}">{note}</div>' if note else '')
                + f'</div>'
            )
        return h

    trans_html = "".join(f'<span class="tpill">{t.get("name","")}</span>' for t in trans)

    if hols:
        hol_html = "".join(
            f'<div class="hol-warn">⚠️ {h if isinstance(h,str) else h.get("name","")}</div>'
            for h in hols
        )
    else:
        hol_html = '<div class="hol-ok">✅ No public holidays</div>'

    if cos:
        co_opts = ""
        for i, ca in enumerate(cos):
            co_opts += (
                f'<label class="co-row">'
                f'<input type="radio" name="co" value="{ca.get("maps_query", ca.get("address",""))}" {"checked" if i==0 else ""}>'
                f'<div><div class="co-name">{ca.get("name","")}</div>'
                f'<div class="co-addr">{ca.get("address","")}</div></div>'
                f'</label>'
            )
        co_opts += (
            '<label class="co-row">'
            '<input type="radio" name="co" value="__custom__">'
            '<div><div class="co-name">Custom address</div>'
            '<input type="text" id="co_inp" class="co_inp" placeholder="Type address…" style="display:none" onclick="event.stopPropagation()"></div>'
            '</label>'
        )
    else:
        co_opts = '<input type="text" id="co_inp" class="glass-inp" placeholder="Enter company address…">'

    tz_from = td.get("origin_tz","").split("/")[-1].replace("_"," ")
    tz_to   = td.get("destination_tz","").split("/")[-1].replace("_"," ")

    css = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{height:100%}
body{
  min-height:100%;font-family:'Inter',system-ui,sans-serif;font-size:14px;color:#fff;
  background:linear-gradient(135deg,#1a1a2e 0%,#16213e 40%,#0f3460 100%);
  background-attachment:fixed;
}

/* ─── HEADER ─── */
.hdr{
  padding:12px 16px;position:sticky;top:0;z-index:100;
  background:rgba(15,15,40,0.85);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
  border-bottom:1px solid rgba(255,255,255,0.08);
  display:flex;align-items:center;justify-content:space-between;gap:10px;
}
.hdr-left{display:flex;align-items:center;gap:11px;min-width:0}
.plane-badge{width:40px;height:40px;border-radius:12px;background:linear-gradient(135deg,#a855f7,#3b82f6);display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0}
.hdr-dest{font-size:18px;font-weight:900;color:#fff;letter-spacing:-0.3px;line-height:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hdr-sub{font-size:11px;color:rgba(255,255,255,0.45);margin-top:2px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hdr-right{display:flex;gap:7px;align-items:center;flex-shrink:0}
.pill{background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.15);color:rgba(255,255,255,0.85);border-radius:20px;padding:5px 11px;font-size:11px;font-weight:700;white-space:nowrap}
.pill-accent{background:linear-gradient(135deg,#a855f7,#3b82f6);border:none}
.pdf-btn{background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.15);color:#fff;border-radius:10px;padding:7px 12px;font-size:12px;font-weight:700;cursor:pointer;white-space:nowrap;flex-shrink:0}
.pdf-btn:hover{background:rgba(255,255,255,0.18)}

/* ─── WEATHER STRIP ─── */
.wx-strip{
  padding:8px 16px;display:flex;align-items:center;gap:10px;
  background:rgba(255,255,255,0.03);border-bottom:1px solid rgba(255,255,255,0.06);
  overflow-x:auto;
}
.wx-label{font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:1px;color:rgba(255,255,255,0.3);white-space:nowrap;flex-shrink:0}
.wc{border-radius:12px;padding:7px 11px;display:flex;align-items:center;gap:8px;flex:0 0 118px;min-height:64px}
.wc-em{font-size:20px;line-height:1}
.wc-day{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;opacity:.7}
.wc-temps{font-size:15px;font-weight:900;line-height:1.1}
.wc-lo{font-size:11px;opacity:.5;font-weight:600}
.wc-cond{font-size:9px;opacity:.65;margin-top:1px;font-weight:600}
.wc-rain{font-size:9px;opacity:.7;margin-top:1px}

/* ─── KEY FACTS STRIP ─── */
.facts-strip{
  display:flex;overflow-x:auto;border-bottom:1px solid rgba(255,255,255,0.06);
  background:rgba(255,255,255,0.02);
  -webkit-overflow-scrolling:touch;
}
.kf{flex:0 0 auto;padding:8px 16px;border-right:1px solid rgba(255,255,255,0.06);min-width:110px}
.kf-label{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:rgba(255,255,255,0.35);margin-bottom:2px}
.kf-val{font-size:13px;font-weight:800;color:#fff;line-height:1.2}
.kf-sub{font-size:10px;color:rgba(255,255,255,0.35);font-weight:500;margin-top:1px}

/* ─── MAIN: mobile = single col, desktop = 3 col ─── */
.main{padding:10px;display:flex;flex-direction:column;gap:10px}
.col-left{order:2}
.col-mid{order:1}
.col-right{order:3}
@media(min-width:900px){
  .main{display:grid;grid-template-columns:38% 37% 25%;align-items:start}
  .col-left,.col-mid,.col-right{order:unset}
}
.col{display:flex;flex-direction:column;gap:10px}

/* ─── CARD ─── */
.card{
  border-radius:16px;background:rgba(255,255,255,0.07);
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  border:1px solid rgba(255,255,255,0.12);overflow:hidden;
}

/* ─── SECTION ─── */
.sec{padding:12px 14px;border-bottom:1px solid rgba(255,255,255,0.06)}
.sec:last-child{border-bottom:none}
.sh{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.sh-ico{width:28px;height:28px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0}
.sh-label{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.8px;color:rgba(255,255,255,0.45)}
.ico-green{background:rgba(52,211,153,0.2)} .ico-amber{background:rgba(251,191,36,0.2)}
.ico-purple{background:rgba(168,85,247,0.2)} .ico-cyan{background:rgba(34,211,238,0.2)}
.ico-orange{background:rgba(251,146,60,0.2)} .ico-blue{background:rgba(96,165,250,0.2)}
.ico-pink{background:rgba(244,114,182,0.2)} .ico-yellow{background:rgba(250,204,21,0.2)}
.ico-teal{background:rgba(20,184,166,0.2)} .ico-red{background:rgba(248,113,113,0.2)}
.ico-lime{background:rgba(163,230,53,0.2)}

/* ─── INPUTS ─── */
.glass-inp{
  width:100%;background:rgba(255,255,255,0.08);border:1.5px solid rgba(255,255,255,0.15);
  border-radius:10px;padding:10px 13px;font-size:15px;font-family:'Inter',sans-serif;
  color:#fff;outline:none;-webkit-appearance:none;
}
.glass-inp::placeholder{color:rgba(255,255,255,0.3)}
.glass-inp:focus{border-color:rgba(168,85,247,0.7);background:rgba(255,255,255,0.11)}
.inp-hint{font-size:11px;color:rgba(255,255,255,0.3);margin-top:5px;font-weight:500}

/* ─── COMPANY ─── */
.co-row{display:flex;align-items:flex-start;gap:9px;padding:10px 11px;border-radius:10px;cursor:pointer;border:1.5px solid rgba(255,255,255,0.1);margin-bottom:6px;background:rgba(255,255,255,0.05)}
.co-row:hover{border-color:rgba(168,85,247,0.5)}
.co-row input[type=radio]{margin-top:3px;accent-color:#a855f7;flex-shrink:0;width:18px;height:18px}
.co-name{font-size:14px;font-weight:700;color:#fff}
.co-addr{font-size:11px;color:rgba(255,255,255,0.4);margin-top:2px}
.co_inp{width:100%;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);border-radius:8px;padding:7px 10px;font-size:13px;color:#fff;margin-top:6px;font-family:'Inter',sans-serif;outline:none}
.co_inp::placeholder{color:rgba(255,255,255,0.3)}
.nav-btn{
  width:100%;margin-top:10px;background:linear-gradient(135deg,#a855f7,#3b82f6);
  color:#fff;border:none;border-radius:12px;padding:13px;font-size:15px;
  font-weight:800;cursor:pointer;font-family:'Inter',sans-serif;
}
.nav-btn:active{opacity:.85}

/* ─── POI ─── */
.poi{padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.06)}
.poi:last-child{border-bottom:none}
.poi-top{display:flex;align-items:flex-start;gap:10px}
.poi-title-row{display:flex;align-items:center;gap:8px;margin-bottom:3px}
.poi-n{width:24px;height:24px;border-radius:7px;background:linear-gradient(135deg,#a855f7,#3b82f6);color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;flex-shrink:0}
.poi-title{font-size:15px;font-weight:700;color:#fff;line-height:1.2}
.poi-meta{font-size:12px;color:rgba(168,85,247,0.95);font-weight:600;margin-top:3px;display:flex;align-items:center;flex-wrap:wrap;gap:6px}
/* collapsible note */
.poi-note{font-size:13px;color:rgba(255,255,255,0.5);line-height:1.6;margin-top:7px;display:none}
.poi-note.open{display:block}
.expand-btn{background:none;border:none;color:rgba(168,85,247,0.7);font-size:11px;font-weight:700;cursor:pointer;padding:0;font-family:'Inter',sans-serif;white-space:nowrap}
.expand-btn:hover{color:#a855f7}
.walk-btn{flex-shrink:0;background:rgba(255,255,255,0.08);border:1.5px solid rgba(255,255,255,0.15);color:rgba(255,255,255,0.8);border-radius:10px;padding:8px 12px;font-size:16px;cursor:pointer;line-height:1}
.walk-btn:hover,.walk-btn:active{background:rgba(168,85,247,0.3)}

/* ─── PLUG ─── */
.plug-row{display:flex;align-items:center;gap:16px}
.plug{text-align:center;flex-shrink:0}
.plug-label{font-size:9px;font-weight:800;color:rgba(250,204,21,0.9);margin-top:5px;text-transform:uppercase;letter-spacing:.5px}
.plug-meta{flex:1}
.plug-v{font-size:17px;font-weight:900;color:#fff;margin-bottom:4px}
.plug-note{font-size:12px;color:rgba(255,255,255,0.45);line-height:1.6;margin-bottom:8px}
.badge{display:inline-flex;align-items:center;gap:5px;border-radius:8px;padding:5px 12px;font-size:12px;font-weight:700}
.b-warn{background:rgba(251,191,36,0.15);color:#fbbf24;border:1px solid rgba(251,191,36,0.3)}
.b-ok  {background:rgba(52,211,153,0.15);color:#34d399;border:1px solid rgba(52,211,153,0.3)}

/* ─── TRANSPORT ─── */
.tpills{display:flex;flex-wrap:wrap;gap:8px}
.tpill{background:rgba(255,255,255,0.08);border:1.5px solid rgba(255,255,255,0.12);color:rgba(255,255,255,0.85);border-radius:20px;padding:7px 16px;font-size:14px;font-weight:700}

/* ─── AIRPORT ─── */
.apt-name{font-size:15px;font-weight:800;color:#fff;margin-bottom:10px}
.apt-stats{display:flex;gap:8px}
.apt-s{background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.1);border-radius:10px;padding:10px;flex:1;text-align:center}
.apt-v{font-size:17px;font-weight:800;color:#fb923c}
.apt-l{font-size:9px;color:rgba(255,255,255,0.4);margin-top:3px;text-transform:uppercase;letter-spacing:.5px;font-weight:600}

/* ─── PROSE ─── */
.prose{font-size:13px;color:rgba(255,255,255,0.55);line-height:1.85}

/* ─── CURRENCY ─── */
.stat-big{font-size:30px;font-weight:900;color:#fff}
.stat-sub{font-size:12px;color:rgba(255,255,255,0.4);margin:3px 0 10px;font-weight:500}
.stat-tags{display:flex;flex-wrap:wrap;gap:7px}
.stag{background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.1);border-radius:8px;padding:6px 12px;font-size:12px;color:rgba(255,255,255,0.65);font-weight:600}

/* ─── HOLIDAYS ─── */
.hol-ok{color:#34d399;font-weight:700;font-size:14px}
.hol-warn{font-size:13px;color:#fbbf24;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.06);font-weight:600}

/* ─── SCROLLBAR ─── */
::-webkit-scrollbar{width:3px;height:3px}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.15);border-radius:3px}

/* ─── PRINT ─── */
@media print{
  body{background:#1a1a2e}
  .hdr{position:static;background:rgba(15,15,40,1)}
  .main{display:grid;grid-template-columns:1fr 1fr 1fr}
  .card{break-inside:avoid}
  .pdf-btn{display:none}
  .poi-note{display:block!important}
  *{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
"""

    js = f"""
var userLat=null,userLon=null,geoTimer=null;

function haversineM(a,b,c,d){{
  var R=6371000,p1=a*Math.PI/180,p2=c*Math.PI/180;
  var dp=(c-a)*Math.PI/180,dl=(d-b)*Math.PI/180;
  var x=Math.sin(dp/2)*Math.sin(dp/2)+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)*Math.sin(dl/2);
  return R*2*Math.atan2(Math.sqrt(x),Math.sqrt(1-x));
}}

function updateWalkTimes(){{
  if(userLat===null)return;
  document.querySelectorAll('.walk-btn[data-lat]').forEach(function(btn){{
    var lat=parseFloat(btn.dataset.lat),lon=parseFloat(btn.dataset.lon);
    if(!isNaN(lat)&&!isNaN(lon)){{
      var dist=haversineM(userLat,userLon,lat,lon);
      var mins=Math.max(1,Math.round(dist/80));
      btn.innerHTML='🗺 '+mins+'m';
    }}
  }});
}}

function showLocBadge(msg){{
  var b=document.getElementById('loc-badge');
  if(b){{b.textContent=msg;b.style.display='block';}}
}}

function geocodeHotel(addr){{
  var q=encodeURIComponent(addr+', {dest}');
  fetch('https://nominatim.openstreetmap.org/search?q='+q+'&format=json&limit=1',{{headers:{{'Accept-Language':'en','User-Agent':'TripBrief/1.0'}}}})
  .then(function(r){{return r.json();}})
  .then(function(d){{
    if(d&&d.length>0){{
      userLat=parseFloat(d[0].lat);userLon=parseFloat(d[0].lon);
      updateWalkTimes();showLocBadge('📍 Hotel location found');
    }} else {{showLocBadge('⚠️ Hotel not found — check address');}}
  }}).catch(function(){{}});
}}

function saveH(v){{
  localStorage.setItem('h',v);
  clearTimeout(geoTimer);
  var badge=document.getElementById('loc-badge');
  if(badge&&v.trim().length===0){{badge.style.display='none';}}
  if(v.trim().length>4){{
    if(badge){{badge.textContent='🔍 Finding location…';badge.style.display='block';}}
    geoTimer=setTimeout(function(){{geocodeHotel(v);}},900);
  }}
}}

function walkTo(dest){{
  var h=(document.getElementById('hi').value||'').trim();
  var url='https://www.google.com/maps/dir/?api=1';
  if(h)url+='&origin='+encodeURIComponent(h);
  else if(userLat)url+='&origin='+userLat+','+userLon;
  url+='&destination='+encodeURIComponent(dest)+'&travelmode=walking';
  window.open(url,'_blank');
}}

function airportNav(airport, city){{
  var h=(document.getElementById('hi').value||'').trim();
  var dest=h||city+' city center';
  window.open('https://www.google.com/maps/dir/?api=1&origin='+encodeURIComponent(airport)+'&destination='+encodeURIComponent(dest)+'&travelmode=transit','_blank');
}}

function toggleNote(id){{
  var el=document.getElementById(id);
  var btn=document.getElementById('btn-'+id);
  if(!el)return;
  var open=el.classList.toggle('open');
  if(btn)btn.textContent=open?'▴ less':'▾ more';
}}

// On load: restore hotel & try GPS
(function(){{
  var s=localStorage.getItem('h');
  if(s&&s.trim().length>0){{
    document.getElementById('hi').value=s;
    geocodeHotel(s);
  }} else if(navigator.geolocation){{
    navigator.geolocation.getCurrentPosition(function(pos){{
      if(userLat===null){{
        userLat=pos.coords.latitude;userLon=pos.coords.longitude;
        updateWalkTimes();showLocBadge('📍 Using your GPS location');
      }}
    }},null,{{timeout:5000}});
  }}
}})();
"""

    H = []
    H.append(f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>✈️ {dest}</title><style>{css}</style></head><body>""")

    # Header
    H.append(f"""<div class="hdr">
  <div class="hdr-left">
    <div class="plane-badge">✈️</div>
    <div style="min-width:0">
      <div class="hdr-dest">{dest}</div>
      <div class="hdr-sub">{origin} · {dfmt} · {nstr}</div>
    </div>
  </div>
  <div class="hdr-right">
    <span class="pill pill-accent">⏱ {dstr}</span>
    <button class="pdf-btn" onclick="window.print()">🖨</button>
  </div>
</div>""")

    # Weather strip
    H.append(f"""<div class="wx-strip">
  <div class="wx-label">Forecast</div>
  {wx_cards}
</div>""")

    # Key facts strip (horizontally scrollable on mobile)
    H.append(f"""<div class="facts-strip">
  <div class="kf"><div class="kf-label">⏰ Time</div><div class="kf-val">{dstr}</div><div class="kf-sub">{tz_to}</div></div>
  <div class="kf"><div class="kf-label">💱 Currency</div><div class="kf-val">{cur.get("symbol","")} {cur.get("code","")}</div><div class="kf-sub">{cur.get("origin_rate", cur.get("approx_usd_rate",""))}</div></div>
  <div class="kf"><div class="kf-label">🔌 Outlet</div><div class="kf-val">Type {", ".join(otypes)}</div><div class="kf-sub">{outlet.get("voltage","")}</div></div>
  <div class="kf"><div class="kf-label">🔄 Adapter</div><div class="kf-val">{"⚠️ Needed" if adapter else "✅ No"}</div></div>
  <div class="kf"><div class="kf-label">💳 Cards</div><div class="kf-val" style="font-size:12px">{cur.get("cards_accepted","")}</div></div>
  <div class="kf"><div class="kf-label">🤝 Tipping</div><div class="kf-val" style="font-size:12px">{cur.get("tipping","")}</div></div>
</div>""")

    # Main
    H.append('<div class="main">')

    # LEFT col — hotel, etiquette, dress code
    H.append('<div class="col col-left">')

    H.append(f'''<div class="card"><div class="sec">
  <div class="sh"><div class="sh-ico ico-green">🏨</div><span class="sh-label">Your Hotel</span></div>
  <input type="text" id="hi" class="glass-inp" placeholder="Hotel name or address…" oninput="saveH(this.value)">
  <div id="loc-badge" style="display:none;font-size:11px;color:#34d399;margin-top:6px;font-weight:600"></div>
  <div class="inp-hint">Walking times update automatically when hotel is set</div>
</div></div>''')

    H.append(f'''<div class="card"><div class="sec">
  <div class="sh"><div class="sh-ico ico-purple">🤝</div><span class="sh-label">Business Etiquette</span></div>
  <div class="prose">{etiq}</div>
</div></div>''')

    H.append(f'''<div class="card"><div class="sec">
  <div class="sh"><div class="sh-ico ico-pink">👔</div><span class="sh-label">Dress Code</span></div>
  <div class="prose">{dress}</div>
</div></div>''')

    H.append('</div>')  # /left col

    # MIDDLE col — currency first, then practical info
    H.append('<div class="col col-mid">')

    H.append(f'''<div class="card"><div class="sec">
  <div class="sh"><div class="sh-ico ico-cyan">💰</div><span class="sh-label">Currency & Payments</span></div>
  <div class="stat-big">{cur.get("symbol","")} {cur.get("code","")}</div>
  <div class="stat-sub">{cur.get("name","")} · {cur.get("origin_rate", cur.get("approx_usd_rate",""))}</div>
  <div class="stat-tags">
    <span class="stag">💳 {cur.get("cards_accepted","")}</span>
    <span class="stag">🤝 {cur.get("tipping","")}</span>
  </div>
</div></div>''')

    H.append(f'''<div class="card"><div class="sec">
  <div class="sh"><div class="sh-ico ico-yellow">🔌</div><span class="sh-label">Power Outlet</span></div>
  <div class="plug-row">
    <div style="display:flex;gap:8px;flex-shrink:0">{outlet_html}</div>
    <div class="plug-meta">
      <div class="plug-v">{outlet.get("voltage","")}</div>
      <span class="badge {'b-warn' if adapter else 'b-ok'}">{"⚠️ Adapter needed" if adapter else "✅ No adapter"}</span>
    </div>
  </div>
</div></div>''')

    H.append(f'''<div class="card"><div class="sec">
  <div class="sh"><div class="sh-ico ico-teal">🚗</div><span class="sh-label">Transport Apps</span></div>
  <div class="tpills">{trans_html}</div>
</div></div>''')

    apt_airport = apt.get("airport_name", f"{dest} Airport")
    H.append(f'''<div class="card"><div class="sec">
  <div class="sh"><div class="sh-ico ico-red">🚌</div><span class="sh-label">Airport Transfer</span></div>
  <div class="apt-name">{apt.get("recommended","")}</div>
  <div class="apt-stats">
    <div class="apt-s"><div class="apt-v">{apt.get("time_mins","?")}m</div><div class="apt-l">Travel</div></div>
    <div class="apt-s"><div class="apt-v">{apt.get("cost_local","?")}</div><div class="apt-l">Local</div></div>
    <div class="apt-s"><div class="apt-v">~${apt.get("cost_usd","?")}</div><div class="apt-l">USD est.</div></div>
  </div>
  <button class="nav-btn" style="margin-top:10px" onclick="airportNav('{apt_airport}','{dest}')">📍 Directions from Airport</button>
</div></div>''')

    H.append(f'''<div class="card"><div class="sec">
  <div class="sh"><div class="sh-ico ico-lime">📅</div><span class="sh-label">Public Holidays</span></div>
  {hol_html}
</div></div>''')

    H.append('</div>')  # /middle col

    # RIGHT col — restaurants & attractions (don't touch)
    H.append('<div class="col col-right">')

    H.append(f'''<div class="card"><div class="sec">
  <div class="sh"><div class="sh-ico ico-orange">🍽️</div><span class="sh-label">Restaurants</span></div>
  {poi_rows(rests, dest)}
</div></div>''')

    H.append(f'''<div class="card"><div class="sec">
  <div class="sh"><div class="sh-ico ico-blue">🗺️</div><span class="sh-label">Attractions</span></div>
  {poi_rows(attr, dest)}
</div></div>''')

    H.append('</div>')  # /right col
    H.append('</div>')  # /main
    H.append(f'<script>{js}</script>')
    H.append('</body></html>')
    return "".join(H)



def generate_pdf(html_content: str, output_path: str) -> bool:
    """
    Try to generate a PDF from the HTML using weasyprint.
    Returns True on success, False if weasyprint is not installed.

    To enable:  pip install weasyprint
    """
    try:
        from weasyprint import HTML
        HTML(string=html_content).write_pdf(output_path)
        return True
    except ImportError:
        return False
    except Exception as e:
        print(f"    ⚠️  PDF generation error: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9: MAIN — Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║      ✈️   SAPIENS SALES TRAVEL BRIEF AGENT                  ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    # Get inputs — from command line or interactive prompts
    if len(sys.argv) in (6, 7):
        origin               = sys.argv[1]
        destination_city     = sys.argv[2]
        destination_country  = sys.argv[3]
        start_date           = sys.argv[4]
        end_date             = sys.argv[5]
        company_name         = sys.argv[6] if len(sys.argv) == 7 else ""
    else:
        print("\n  Enter your trip details:\n")
        origin              = input("  Origin city (e.g. Tel Aviv):         ").strip()
        destination_city    = input("  Destination city (e.g. London):      ").strip()
        destination_country = input("  Destination country (e.g. UK):       ").strip()
        start_date          = input("  Arrival date   (YYYY-MM-DD):         ").strip()
        end_date            = input("  Departure date (YYYY-MM-DD):         ").strip()
        company_name        = input("  Company being visited (optional):    ").strip()

    # Run the agent — this is the main work
    data = run_agent(origin, destination_city, destination_country, start_date, end_date, company_name)

    if not data:
        print("\n❌  Agent returned no data. Please check your API key and try again.")
        sys.exit(1)

    # Save output files
    output_dir = Path(__file__).parent
    slug       = f"{destination_city.lower().replace(' ', '_')}_{start_date}"
    html_path  = output_dir / f"travel_brief_{slug}.html"
    pdf_path   = output_dir / f"travel_brief_{slug}.pdf"

    print("\n  📄  Generating HTML report...")
    html_content = generate_html(data)
    html_path.write_text(html_content, encoding="utf-8")
    print(f"  ✅  Saved: {html_path.name}")

    print("  📄  Generating PDF...")
    if generate_pdf(html_content, str(pdf_path)):
        print(f"  ✅  Saved: {pdf_path.name}")
    else:
        print("  ℹ️   PDF skipped — weasyprint not installed.")
        print("       Option A: pip install weasyprint  then run again.")
        print("       Option B: open the HTML file, press Ctrl+P → Save as PDF.")

    print()
    print(f"  ✅  Done!  Travel brief ready for {destination_city}.")
    print(f"       Open {html_path.name} in your browser to view it.")
    print()


if __name__ == "__main__":
    main()
