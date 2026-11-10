import os
import random
from dotenv import load_dotenv
from google import genai

load_dotenv()

API_KEY = os.getenv("LLM_API_KEY", "mock")
MODEL_NAME = "gemini-1.5-flash"

async def generate_comment(post_text: str, persona: str, tone: str) -> str:
    if API_KEY == "mock" or not API_KEY:
        samples = ["Honestly spot on...", "Been thinking about this...", "Hard to argue with this."]
        return f"{random.choice(samples)} [Persona: {persona[:20]}...]"

    prompt = (
        f"Target Post Content: \"{post_text}\"\n"
        f"Your Assigned Persona: {persona}\n"
        f"Campaign Tone: {tone}\n\n"
        "Write an authentic, human-sounding reply under 25 words directly addressing the post. "
        "Do NOT use hashtags, quotes, or robotic phrases like 'Great post!'."
    )

    try:
        # The official Google GenAI client natively authenticates the token format
        client = genai.Client(api_key=API_KEY)
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        if response and response.text:
            return response.text.strip()
        return "Interesting perspective!"
    except Exception as e:
        print(f"[!] GenAI SDK Error: {e}")
        # Graceful fallback ensures your test run never blocks on API quirks
        samples = ["Really insightful point.", "Completely agree with this view.", "Spot on assessment."]
        return random.choice(samples)