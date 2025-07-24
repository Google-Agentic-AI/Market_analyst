# import base64
# import datetime
# import json
# import os
# import asyncio
# from typing import Optional
# from zoneinfo import ZoneInfo

# import google.auth
# import requests
# from google.cloud import aiplatform
# # Use the modern v3 Translation client
# from google.cloud import translate
# from google.adk.agents import Agent
# from vertexai.generative_models import GenerativeModel, Part

# # --- Configuration ---
# try:
#     _, project_id = google.auth.default()
#     os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
# except google.auth.exceptions.DefaultCredentialsError:
#     print("WARNING: Google Cloud credentials not found. Run 'gcloud auth application-default login' for local development.")
#     # You MUST replace this with your actual project ID if not using gcloud auth
#     project_id = "exalted-bonus-466604-j4"

# os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
# # This tells the ADK to use Vertex AI as the backend for the main agent LLM
# os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

# # --- Initialize API Clients ---
# # Initialize clients once to be reused.
# translate_client = translate.TranslationServiceClient()
# location = "global"
# parent = f"projects/{project_id}/locations/{location}"


# # --- Deployed Model & API Key Configuration ---
# ENDPOINT_ID = "8158971113888546816" # Your custom image classification model endpoint ID
# MARKET_API_KEY = "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b"  # Your data.gov.in API Key

# # =========================================================================
# # === TOOLS (Functions the AI can use) ===
# # =========================================================================

# async def translate_to_english(text: str) -> str:
#     """Translates a given text string into English. Use this to convert non-English crop names to English before calling the market analysis tool."""
#     print(f"Tool called: translate_to_english for text='{text}'")
#     try:
#         # Use the v3 client
#         response = translate_client.translate_text(
#             parent=parent,
#             contents=[text],
#             mime_type="text/plain",
#             source_language_code=None,  # Auto-detect source language
#             target_language_code="en-US",
#         )
#         translated_text = response.translations[0].translated_text
#         print(f"Translation result: '{text}' -> '{translated_text}'")
#         return translated_text
#     except Exception as e:
#         print(f"Error during translation: {e}")
#         return text # Fallback to original text if translation fails

# async def diagnose_crop_disease(image_b64: str) -> str:
#     """Analyzes a base64 encoded image string of a plant leaf to diagnose diseases."""
#     print("Tool called: diagnose_crop_disease")
#     if not image_b64 or not isinstance(image_b64, str):
#         return "Error: Image data was not provided in the correct format."
#     if image_b64.startswith("[Image Data for Tool Use: "):
#         image_b64 = image_b64.replace("[Image Data for Tool Use: ", "").strip("]")
#     try:
#         instances = [{"content": image_b64}]
#         endpoint = aiplatform.Endpoint(endpoint_name=f"projects/{project_id}/locations/us-central1/endpoints/{ENDPOINT_ID}")
#         prediction_response = await asyncio.to_thread(endpoint.predict, instances=instances)
#         prediction = prediction_response.predictions
#         if not prediction or not prediction[0].get('confidences'):
#             return "The model could not identify the plant or disease from the image. Please try a clearer picture."
#         confidences = prediction[0]['confidences']
#         display_names = prediction[0]['displayNames']
#         disease_name = display_names[confidences.index(max(confidences))]
#         print(f"Classification Model Diagnosis: {disease_name}")
#     except Exception as e:
#         print(f"ERROR calling Vertex AI Endpoint: {e}")
#         return f"Sorry, I was unable to analyze the image with the diagnosis model. Error: {e}"
#     if "healthy" in disease_name.lower():
#         return "healthy"
#     llm = GenerativeModel("gemini-2.0-flash")
#     prompt = f"""
#     A farmer's plant has been diagnosed with: '{disease_name}'.
#     Act as a helpful agricultural expert. Provide a simple, clear, and actionable summary including:
#     1. Diagnosis: A brief description of '{disease_name}'.
#     2. Common Causes: List the typical reasons this disease appears.
#     3. Recommended Actions: A step-by-step treatment plan (Organic and Chemical).
#     4. Important Links: Provide placeholder links for more info.
#     """
#     response = await llm.generate_content_async(prompt)
#     return response.text

# async def get_market_analysis(commodity: str, user_language: str, market: Optional[str] = None) -> str:
#     """
#     Fetches market price data for a given agricultural commodity. The commodity name MUST be in English.
#     Args:
#         commodity (str): The English name of the crop, e.g., 'Tomato'.
#         user_language (str): The original language of the user's query, e.g., 'English', 'Bengali', 'Hindi'.
#         market (Optional[str]): The specific APMC market. This is optional.
#     """
#     print(f"Tool called: get_market_analysis for '{commodity}' in '{market}' with language '{user_language}'")
#     BASE_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
#     llm = GenerativeModel("gemini-2.0-flash")
#     prompt = ""
#     try:
#         if market:
#             print(f"Fetching 7-day trend for {commodity} in {market}...")
#             historical_data = []
#             today = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
#             for i in range(7):
#                 query_date = today - datetime.timedelta(days=i)
#                 formatted_date = query_date.strftime("%d/%m/%Y")
#                 params = {"api-key": MARKET_API_KEY, "format": "json", "limit": 10, "filters[commodity]": commodity, "filters[market]": market, "filters[arrival_date]": formatted_date}
#                 response = await asyncio.to_thread(requests.get, BASE_URL, params=params)
#                 response.raise_for_status()
#                 records = response.json().get("records", [])
#                 if records: historical_data.extend(records)
#             if not historical_data: return f"Sorry, I couldn't find any data for {commodity} in {market} market in the last 7 days."
#             raw_data_str = json.dumps(historical_data, indent=2)
#             prompt = f"""
#             Analyze the following market data for {commodity} from the {market} market.
#             **CRITICAL INSTRUCTION: Your entire response must be in {user_language}.**
#             Data: ```json\n{raw_data_str}\n```
#             Provide a concise summary for a farmer, including the most recent price ('modal_price') and any trend.
#             """
#         else:
#             print(f"Fetching general data for {commodity} across all markets...")
#             params = {"api-key": MARKET_API_KEY, "format": "json", "limit": 100, "filters[commodity]": commodity}
#             response = await asyncio.to_thread(requests.get, BASE_URL, params=params)
#             response.raise_for_status()
#             records = response.json().get("records", [])
#             if not records: return f"Sorry, I couldn't find any recent price data for {commodity}."
#             raw_data_str = json.dumps(records, indent=2)
#             prompt = f"""
#             The user asked for the price of '{commodity}'.
#             **CRITICAL INSTRUCTION: Your entire response must be in {user_language}.**
#             Data from various markets: ```json\n{raw_data_str}\n```
#             Your task is to:
#             1. Summarize the price range ('modal_price').
#             2. List prices from 4-5 different markets.
#             3. After the summary, ask the user in {user_language} if they want a detailed analysis for a specific market.
#             """
#     except Exception as e:
#         return f"An error occurred while fetching market data: {e}"
    
#     analysis_response = await llm.generate_content_async(prompt)
#     return analysis_response.text

# async def get_weather(query: str) -> str:
#     """Gets the current weather."""
#     return "It's 90 degrees and sunny."

# async def get_current_time(query: str) -> str:
#     """Gets the current time."""
#     return datetime.datetime.now().strftime("%I:%M %p")

# # =========================================================================
# # === AGENT DEFINITION WITH MANUAL PREPROCESSING ===
# # =========================================================================

# class KisanSathiAgent(Agent):
#     async def _preprocess_async(self, request, **kwargs):
#         if not request.history: return await super()._preprocess_async(request, **kwargs)
#         last_user_message = request.history[-1]
#         if last_user_message.role == "user" and any(hasattr(p, 'inline_data') and p.inline_data for p in last_user_message.parts):
#             image_part = next((p for p in last_user_message.parts if hasattr(p, 'inline_data') and p.inline_data), None)
#             if image_part:
#                 print("Found an image in the prompt. Preprocessing...")
#                 image_bytes = image_part.inline_data.data
#                 image_b64 = base64.b64encode(image_bytes).decode("utf-8")
                
#                 # This logic constructs a direct tool call, bypassing the need for the LLM to decide.
#                 from google.generativeai.types import content_types
#                 tool_call = content_types.FunctionCall(
#                     name='diagnose_crop_disease',
#                     args={'image_b64': image_b64}
#                 )
#                 request.history[-1] = content_types.to_content(tool_call)
#         return await super()._preprocess_async(request, **kwargs)

# # Instantiate the custom agent
# root_agent = KisanSathiAgent(
#     name="root_agent",
#     model="gemini-2.0-flash",
#     instruction="""You are 'KisanSathi', a helpful and friendly AI assistant for Indian farmers. 
#     Your primary goal is to always respond in the language of the user's most recent query.
    
#     **CRITICAL RULE: When you reply in an Indian language (like Hindi, Bengali, Punjabi, etc.), you MUST use its native script (e.g., Devanagari for Hindi, Gurmukhi for Punjabi, Bengali script for Bengali), NOT Roman transliteration.**

#     **Core Workflow:**
#     1.  **Identify Language:** Determine the user's language (e.g., 'English', 'Bengali', 'Hindi', 'Punjabi').
#     2.  **Identify Intent:** Understand if the user wants market prices, disease diagnosis, weather, or time.

#     **Tool Usage Rules:**
#     - **`get_market_analysis` Tool:**
#         - This tool **requires the commodity name in English**.
#         - If the user provides a commodity name in another language (e.g., 'ਟਮਾਟਰ'), you MUST first use the `translate_to_english` tool to get the English name.
#         - Then, call `get_market_analysis` with the translated English commodity name and the user's original language.
#         - Example: User says "ਟਮਾਟਰ ਦਾ ਕੀ ਭਾਅ ਹੈ?".
#             - Step 1: Call `translate_to_english(text='ਟਮਾਟਰ')`. It returns "Tomato".
#             - Step 2: Call `get_market_analysis(commodity='Tomato', user_language='Punjabi')`.
#     - **`diagnose_crop_disease` Tool:**
#         - This tool is called automatically when an image is uploaded. You don't need to call it yourself.
#         - If the result is "healthy", get the crop name and then follow the `get_market_analysis` workflow.
#         - If it's a disease, just show the result.
#     """,
#     tools=[
#         diagnose_crop_disease,
#         get_market_analysis,
#         get_weather,
#         get_current_time,
#         translate_to_english
#     ],
# )

import base64
import datetime
import json
import os
import asyncio
from typing import Optional
from zoneinfo import ZoneInfo

import google.auth
import requests
from google.cloud import aiplatform
from google.cloud import translate # Use the modern v3 Translation client
from google.adk.agents import Agent
from vertexai.generative_models import GenerativeModel, Part

# --- Configuration ---
try:
    _, project_id = google.auth.default()
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
except google.auth.exceptions.DefaultCredentialsError:
    print("WARNING: Google Cloud credentials not found. Run 'gcloud auth application-default login' for local development.")
    project_id = "your-gcp-project-id" # Fallback if needed

os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

# --- Initialize API Clients ---
translate_client = translate.TranslationServiceClient()
location = "global"
parent = f"projects/{project_id}/locations/{location}"

# --- Deployed Model & API Key Configuration ---
ENDPOINT_ID = "8158971113888546816" # Your custom image classification model endpoint ID
MARKET_API_KEY = "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b" # Your data.gov.in API Key

# =========================================================================
# === TOOLS (Functions the AI can use) ===
# =========================================================================

async def diagnose_crop_disease(image_b64: str) -> str:
    # This function is fine, no changes needed.
    """Analyzes a base64 encoded image string of a plant leaf to diagnose diseases."""
    print("Tool called: diagnose_crop_disease")
    if not image_b64: return "Error: No image data was provided to the tool."
    if image_b64.startswith("[Image Data for Tool Use: "):
        image_b64 = image_b64.replace("[Image Data for Tool Use: ", "").strip("]")
    try:
        instances = [{"content": image_b64}]
        endpoint = aiplatform.Endpoint(endpoint_name=f"projects/{project_id}/locations/us-central1/endpoints/{ENDPOINT_ID}")
        prediction_response = await asyncio.to_thread(endpoint.predict, instances=instances)
        prediction = prediction_response.predictions
        if not prediction or not prediction[0].get('confidences'): return "The model could not identify the plant or disease from the image."
        confidences, display_names = prediction[0]['confidences'], prediction[0]['displayNames']
        disease_name = display_names[confidences.index(max(confidences))]
        print(f"Classification Model Diagnosis: {disease_name}")
    except Exception as e:
        print(f"ERROR calling Vertex AI Endpoint: {e}")
        return f"Sorry, I was unable to analyze the image with the diagnosis model. Error: {e}"
    if "healthy" in disease_name.lower(): return "healthy"
    llm = GenerativeModel("gemini-2.0-flash")
    prompt = f"A farmer's plant is diagnosed with: '{disease_name}'. As an agricultural expert, provide a simple, actionable summary including Diagnosis, Common Causes, Recommended Actions (Organic and Chemical), and placeholder links."
    response = await llm.generate_content_async(prompt)
    return response.text

async def get_market_analysis(commodity: str, market: Optional[str] = None) -> str:
    """
    Fetches market price data for a given commodity and optional market. 
    It automatically handles different languages for the commodity name.
    Use this for any questions about crop prices.

    Args:
        commodity (str): The name of the crop in any language (e.g., 'Tomato', 'टमाटर', 'টমেটো').
        market (Optional[str]): The specific market name.
    """
    print(f"Tool called: get_market_analysis for '{commodity}' in '{market}'")
    
    # --- Step 1: Translate commodity and market to English for the API call ---
    try:
        # Translate the commodity
        translate_response = translate_client.translate_text(
            parent=parent, contents=[commodity], target_language_code="en-US"
        )
        english_commodity = translate_response.translations[0].translated_text.title()

        # Translate the market if it exists
        english_market = None
        if market:
            translate_response_market = translate_client.translate_text(
                parent=parent, contents=[market], target_language_code="en-US"
            )
            english_market = translate_response_market.translations[0].translated_text.title()
        
        print(f"Translated to: Commodity='{english_commodity}', Market='{english_market}' for API call.")

    except Exception as e:
        print(f"Translation failed: {e}. Using original terms.")
        english_commodity = commodity.title()
        english_market = market.title() if market else None
        
    # --- Step 2: Fetch data using the translated terms ---
    BASE_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
    records = []
    try:
        if english_market:
            # *** THIS IS THE CORRECTED LOGIC ***
            # If a market is specified, ALWAYS fetch the last 7 days of data for a trend analysis.
            print(f"Fetching 7-day trend for {english_commodity} in {english_market}...")
            all_records = []
            today = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
            for i in range(7):
                query_date = today - datetime.timedelta(days=i)
                formatted_date = query_date.strftime("%d/%m/%Y")
                params = {
                    "api-key": MARKET_API_KEY, "format": "json", "limit": 100,
                    "filters[commodity]": english_commodity,
                    "filters[market]": english_market,
                    "filters[arrival_date]": formatted_date,
                }
                response = await asyncio.to_thread(requests.get, BASE_URL, params=params)
                # We don't raise for status here, as some days may have no data which is okay.
                if response.status_code == 200:
                    day_records = response.json().get("records", [])
                    if day_records:
                        all_records.extend(day_records)
            records = all_records
        else:
            # If no market is specified, get the latest general data from many markets
            print(f"Fetching general data for {english_commodity} across all markets...")
            params = {"api-key": MARKET_API_KEY, "format": "json", "limit": 100, "filters[commodity]": english_commodity}
            response = await asyncio.to_thread(requests.get, BASE_URL, params=params)
            response.raise_for_status()
            records = response.json().get("records", [])

        if not records:
            # Use the original commodity name in the error message for the user
            return json.dumps([{"error": f"Sorry, I couldn't find any recent price data for {commodity}."}])

    except requests.exceptions.RequestException as e:
        return json.dumps([{"error": f"Sorry, I had a problem getting data from the market API: {e}"}])

    # --- Step 3: Return the raw data as a JSON string ---
    return json.dumps(records)

async def get_weather(query: str) -> str:
    """Gets the current weather."""
    return "It's 90 degrees and sunny."

async def get_current_time(query: str) -> str:
    """Gets the current time."""
    return datetime.datetime.now().strftime("%I:%M %p")

# =========================================================================
# === AGENT DEFINITION (SIMPLIFIED INSTRUCTIONS) ===
# =========================================================================

class KisanSathiAgent(Agent):
    async def _preprocess_async(self, request, **kwargs):
        if not request.history: return await super()._preprocess_async(request, **kwargs)
        last_user_message = request.history[-1]
        if last_user_message.role == "user" and any(hasattr(p, 'inline_data') and p.inline_data for p in last_user_message.parts):
            image_part = next((p for p in last_user_message.parts if hasattr(p, 'inline_data') and p.inline_data), None)
            if image_part:
                print("Found an image in the prompt. Preprocessing...")
                image_bytes = image_part.inline_data.data
                image_b64 = base64.b64encode(image_bytes).decode("utf-8")
                from google.generativeai.types import content_types
                tool_call = content_types.FunctionCall(name='diagnose_crop_disease', args={'image_b64': image_b64})
                request.history[-1] = content_types.to_content(tool_call)
        return await super()._preprocess_async(request, **kwargs)

root_agent = KisanSathiAgent(
    name="root_agent",
    model="gemini-2.0-flash",
    instruction="""You are 'KisanSathi', a helpful and friendly AI assistant for Indian farmers. 
    Your primary goal is to always respond in the language of the user's most recent query.
    
    **CRITICAL RULE: When you reply in an Indian language (like Hindi, Bengali, Punjabi, etc.), you MUST use its native script (e.g., Devanagari for Hindi, Gurmukhi for Punjabi, Bengali script for Bengali), NOT Roman transliteration.**

    **Tool Behavior:**
    - When you use the `get_market_analysis` tool, it will return raw JSON data. 
    - Your job is to analyze this JSON data and present a clear, helpful summary to the user in their original language.
    - **If the data returned is for a different location than what the user asked for (e.g., they asked for Uttarakhand but the data is for Uttar Pradesh), you must state this clearly in your response.**
    - If the user asks for a specific market, summarize the trend for that market using the historical data provided.
    - If the user does not specify a market, summarize the overall price range from the data and list 3-4 examples. Then, ask if they want more detail on a specific market.

    **Image Workflow:**
    - If the user uploads an image, the `diagnose_crop_disease` tool is called automatically. 
    - If the result is 'healthy', find out the crop name and call `get_market_analysis`.
    - If it's a disease, just show the result.
    """,
    tools=[
        diagnose_crop_disease,
        get_market_analysis,
        get_weather,
        get_current_time
    ],
)