import datetime
import os
import requests
import json
from zoneinfo import ZoneInfo
from typing import Optional, Union
from PIL import Image

import google.auth
from google.adk.agents import Agent
from vertexai.generative_models import GenerativeModel

# --- Import your specialist agent from its file ---
from app.disease_agent import disease_diagnosis_agent

# --- Configuration ---
_, project_id = google.auth.default()
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")


# =========================================================================
# === 🤩 MARKET ANALYSIS TOOL 🤩 ===
# =========================================================================
def get_market_analysis(commodity: str, market: Optional[str] = None) -> str:
    """
    Fetches market price data for a given commodity. If a specific market is provided, it gives a detailed 7-day trend analysis for that location. 
    If no market is provided, it gives a summary of prices across all available markets for that commodity and asks the user to specify a market for a detailed analysis.
    Use this tool when a user asks about crop prices.

    Args:
        commodity (str): The name of the crop, e.g., 'Tomato' or 'টমেটো'.
        market (Optional[str]): The specific APMC market. This is optional.
    """
    print(f"Tool called: get_market_analysis with commodity='{commodity}', market='{market}'")

    BASE_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
    API_KEY = "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b"

    model = GenerativeModel("gemini-2.0-flash")

    if market:
        # --- SCENARIO 1: Market is specified (7-day trend logic) ---
        print(f"Fetching 7-day trend for {commodity} in {market}...")
        historical_data = []
        today = datetime.datetime.now()

        for i in range(7):
            query_date = datetime.datetime(2025, 7, 22) - datetime.timedelta(days=i) # Adjusted for demo data
            formatted_date = query_date.strftime("%d/%m/%Y")

            params = {
                "api-key": API_KEY, "format": "json", "limit": 10,
                "filters[commodity]": commodity, "filters[market]": market,
                "filters[arrival_date]": formatted_date,
            }
            try:
                response = requests.get(BASE_URL, params=params)
                response.raise_for_status()
                records = response.json().get("records", [])
                if records:
                    historical_data.extend(records)
            except requests.exceptions.RequestException:
                pass

        if not historical_data:
            return f"Sorry, I couldn't find any data for {commodity} in {market} market in the last 7 days."

        raw_data_str = json.dumps(historical_data, indent=2)
        prompt = f"""
        You are an expert agricultural market analyst for Indian farmers.
        Analyze the following 7-day market data for {commodity} from the {market} market.
        Data: ```json\n{raw_data_str}\n```
        Your task is to provide a concise sales recommendation. State the most recent day's average price ('modal_price') and the overall trend (rising, falling, or stable).
        Respond in the user's language.
        Example in Bengali: "আজ কোলারে টমেটোর দাম প্রায় ₹3800 প্রতি কুইন্টাল। গত সপ্তাহের তুলনায় দাম কিছুটা বেড়েছে। বিক্রি করার জন্য এটি একটি ভালো দিন।"
        """
    else:
        # --- SCENARIO 2: No market specified (General summary) ---
        print(f"Fetching general data for {commodity} across all markets...")
        params = {"api-key": API_KEY, "format": "json", "limit": 50, "filters[commodity]": commodity}
        try:
            response = requests.get(BASE_URL, params=params)
            response.raise_for_status()
            records = response.json().get("records", [])
            if not records:
                return f"Sorry, I couldn't find any recent price data for {commodity} in any market."
            
            raw_data_str = json.dumps(records, indent=2)
            prompt = f"""
            You are an expert agricultural market analyst. The user asked for the price of {commodity} without specifying a market. 
            Here is recent data from various markets: ```json\n{raw_data_str}\n```
            Your task:
            1. Briefly summarize the general price range (min and max 'modal_price').
            2. List 3-4 different markets and their prices.
            3. Proactively ask the user if they want a detailed 7-day analysis for a specific market.
            Respond in the user's language.
            """
        except requests.exceptions.RequestException:
            return "Sorry, I'm having trouble fetching market data right now."
    
    analysis_response = model.generate_content(prompt)
    return analysis_response.text

# =========================================================================
# === WRAPPER FUNCTION TO MAKE THE DISEASE AGENT A CALLABLE TOOL ===
# =========================================================================
def run_disease_diagnosis(image: Union[Image.Image, bytes]) -> str:
    """
    Use this tool to analyze an image of a plant leaf to check for diseases. Provide the image as input.
    This tool will return a full diagnosis and treatment plan, or the word 'healthy' if the plant is fine.
    
    Args:
        image (Union[Image.Image, bytes]): The image of the plant leaf.
    """
    print("Root agent is calling the disease_diagnosis_agent...")
    # This loop synchronously runs the agent and captures the final tool output
    result = ""
    for event in disease_diagnosis_agent.run(image):
        if event.event_type == "tool_output":
            result = event.content
    return result

# =========================================================================
# === EXISTING EXAMPLE TOOLS ===
# =========================================================================
def get_weather(query: str) -> str:
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."

def get_current_time(query: str) -> str:
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"

# =========================================================================
# === ROOT AGENT DEFINITION (The Master Orchestrator) ===
# =========================================================================
root_agent = Agent(
    name="root_agent",
    model="gemini-2.0-flash", 
    instruction="""You are 'KisanSathi', a master AI assistant for Indian farmers. Your primary goal is to always respond in the same language as the user's last query (e.g., if asked in Bengali, reply in Bengali).

You have access to specialist tools:
1.  A 'run_disease_diagnosis' tool for analyzing plant health from images.
2.  A 'get_market_analysis' tool for crop prices.

**Your workflow logic is as follows:**
- If the user provides an image, you MUST first call the 'run_disease_diagnosis' tool with that image.
- **IF** the result from the diagnosis tool is the exact single word 'healthy', your next action MUST be to call the 'get_market_analysis' tool for the relevant crop (e.g., if it's a tomato leaf, use 'Tomato'). You must then combine the results into a final response, first stating the crop is healthy, and then providing the market analysis.
- **IF** the diagnosis tool returns any other text (like a disease name and treatment), you should provide that information directly to the user and STOP. Do not call the market analysis tool.
- If the user asks about prices, weather, or time directly without an image, use the appropriate tool ('get_market_analysis', 'get_weather', etc.).
""",
    tools=[
        run_disease_diagnosis,
        get_market_analysis,
        get_weather,
        get_current_time
    ],
)