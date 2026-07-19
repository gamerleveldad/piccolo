import os
import requests
from dotenv import load_dotenv

load_dotenv()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def test_discord_payloads():
    if not DISCORD_WEBHOOK_URL:
        print("Error: DISCORD_WEBHOOK_URL not found in .env file.")
        return

    # Simulate the JSON array that Gemini would return
    mocked_gemini_response = [
        {
            "title": "Brave New Wonders", 
            "update": "Release Date changed from TBD to October 24, 2026. A new gameplay deep-dive trailer has been released on official channels."
        },
        {
            "title": "Fire Emblem Fortunes Weave", 
            "update": "Version 1.2.0 patch notes released. Adds new DLC characters and stability improvements to the battle camera."
        },
        {
            "title": "Orbitals", 
            "update": "Metacritic score has settled at 88 based on 64 critic reviews. Expansion roadmap revealed for Q1."
        }
    ]

    print("Simulating Daily Scan Discord Posts...")
    
    for update in mocked_gemini_response:
        title = update["title"]
        message = update["update"]
        
        payload = {"content": f"**DAILY UPDATE - {title}**\n{message}"}
        
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        if response.status_code == 204:
            print(f"Successfully posted mock update for {title}")
        else:
            print(f"Failed to post to Discord: {response.status_code}")

if __name__ == "__main__":
    test_discord_payloads()