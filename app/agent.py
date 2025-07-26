import json
import os
from typing import Optional
import pandas as pd
import google.auth
from google.adk.agents import Agent
from vertexai.generative_models import Part # Part is included for future image handling

# --- Configuration ---
try:
    _, project_id = google.auth.default()
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
except google.auth.exceptions.DefaultCredentialsError:
    print("WARNING: Google Cloud credentials not found. Run 'gcloud auth application-default login' for local development.")
    project_id = "your-gcp-project-id" # Fallback, replace if needed

os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

# --- Load and Prepare Market Data from CSV ---
try:
    CSV_PATH = os.path.join("app", "market_data.csv")
    MARKET_DATA_DF = pd.read_csv(CSV_PATH)
    
    # Clean up column names (e.g., 'Min_x0020_Price' -> 'Min Price')
    # This leaves 'Arrival_Date' as is, which is correct.
    MARKET_DATA_DF.columns = [col.replace('_x0020_', ' ') for col in MARKET_DATA_DF.columns]
    
    # Convert 'Arrival_Date' column to datetime objects for sorting and analysis
    # This uses the correct column name from the CSV.
    MARKET_DATA_DF['Arrival_Date'] = pd.to_datetime(MARKET_DATA_DF['Arrival_Date'], format='%d/%m/%Y')
    
    print(f"Successfully loaded and processed market data from {CSV_PATH}")
    print("Available columns:", MARKET_DATA_DF.columns.tolist())

except FileNotFoundError:
    print(f"ERROR: '{CSV_PATH}' not found. Please create the CSV file and place it in the 'app' directory.")
    MARKET_DATA_DF = pd.DataFrame()

# =========================================================================
# === TOOLS (Functions the AI can use) ===
# =========================================================================

async def get_market_analysis(
    commodity: str,
    state: Optional[str] = None,
    district: Optional[str] = None,
    market: Optional[str] = None,
) -> str:
    """
    Searches a local database for market price data for a given agricultural commodity.
    It can be filtered by state, district, or a specific market.

    Args:
        commodity (str): The English name of the crop (e.g., 'Tomato', 'Potato').
        state (Optional[str]): The English name of the state (e.g., 'West Bengal').
        district (Optional[str]): The English name of the district (e.g., 'Agra').
        market (Optional[str]): The specific English market name (e.g., 'Achnera').
    """
    print(f"Tool called: Searching for Commodity='{commodity}', State='{state}', District='{district}', Market='{market}'")
    
    if MARKET_DATA_DF.empty:
        return json.dumps({"error": "Market data file is not loaded or is empty."})
        
    filtered_df = MARKET_DATA_DF.copy()

    # Apply filters one by one. The matching is case-insensitive and partial.
    if commodity:
        filtered_df = filtered_df[filtered_df['Commodity'].str.contains(commodity, case=False, na=False)]
    if state:
        filtered_df = filtered_df[filtered_df['State'].str.contains(state, case=False, na=False)]
    if district:
        filtered_df = filtered_df[filtered_df['District'].str.contains(district, case=False, na=False)]
    if market:
        filtered_df = filtered_df[filtered_df['Market'].str.contains(market, case=False, na=False)]

    if filtered_df.empty:
        return json.dumps({"error": f"Sorry, I couldn't find any price data for '{commodity}' with the specified location filters."})

    # Convert the date back to string format for JSON serialization
    filtered_df['Arrival_Date'] = filtered_df['Arrival_Date'].dt.strftime('%d/%m/%Y')

    result_json = filtered_df.to_json(orient="records")
    print(f"Found {len(filtered_df)} records. Returning JSON to agent.")
    return result_json

# =========================================================================
# === AGENT DEFINITION ===
# =========================================================================
root_agent = Agent(
    name="root_agent",
    model="gemini-2.0-flash",
    instruction="""You are 'KisanSathi', an expert agricultural market advisor for Indian farmers.
    Your primary goal is to always respond in the language of the user's most recent query.
    
    **CRITICAL RULE: NATIVE SCRIPT:** When you reply in an Indian language (e.g., Hindi, Bengali), you MUST use its native script (e.g., Devanagari, Bengali), NOT Roman transliteration.

    **TOOL INSTRUCTIONS:**
    - The `get_market_analysis` tool returns raw JSON data about crop prices. Your job is to analyze this JSON and present a clear, helpful summary to the user in their language.
    - The data includes fields: 'State', 'District', 'Market', 'Commodity', 'Variety', 'Min Price', 'Max Price', 'Modal Price', and 'Arrival_Date'. The prices are per quintal (100 kg).

    **RESPONSE LOGIC:**
    1.  **General Query (No Market specified):**
        - If the user asks for a price without a specific market, call the tool with just the commodity.
        - From the returned JSON, find the highest and lowest `Modal Price`.
        - Present a summary of the price range.
        - List 3-4 specific examples from the data.
        - End by asking if they want a detailed price trend for a specific market.

    2.  **Specific Market Query / Trend Analysis:**
        - If the user asks for a price or trend in a specific market, call the tool with the commodity and market.
        - Analyze the `Modal Price` for each `Arrival_Date` in the JSON data to identify the trend.
        - Describe the trend clearly (e.g., "The price increased from ₹3000 on July 20th to ₹3500 on July 26th.").
        - Based on the trend, give a simple recommendation about selling.
        - If you only get data for one day, state the price for that day and explicitly say "I only have data for one day, so I cannot determine a trend."

    3.  **Location Mismatch Handling:**
        - If the user asks for a location (e.g., 'Uttarakhand') but the JSON data shows a different location (e.g., 'Uttar Pradesh'), you **must** point this out clearly.

    4.  **Error Handling:**
        - If the tool result contains an 'error' key in the JSON, inform the user you could not find the data.
    """,
    tools=[
        get_market_analysis,
    ],
)