import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import re

TARGET_URL = "https://footfytv.pro/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://footfytv.pro/",
}

def fetch_matches():
    # Python-এর নিজস্ব বিল্ট-ইন UTC সময় ব্যবহার করা হয়েছে
    current_utc_time = datetime.now(timezone.utc).isoformat()

    matches_data = {
        "last_updated_utc": current_utc_time,
        "live": [],
        "upcoming": [],
        "finished": []
    }

    try:
        response = requests.get(TARGET_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching target website: {e}")
        return matches_data

    soup = BeautifulSoup(response.text, "html.parser")
    
    match_cards = soup.select(".match-item, .match-card, div[data-match-id]") 

    for card in match_cards:
        try:
            match_id = card.get("data-match-id") or card.get("id") or "N/A"
            status = card.get("data-status", "").lower()
            
            home_team_el = card.select_one(".home-team, .team-home")
            away_team_el = card.select_one(".away-team, .team-away")
            
            home_name = home_team_el.text.strip() if home_team_el else "Unknown"
            away_name = away_team_el.text.strip() if away_team_el else "Unknown"
            
            home_logo = home_team_el.find("img")["src"] if home_team_el and home_team_el.find("img") else ""
            away_logo = away_team_el.find("img")["src"] if away_team_el and away_team_el.find("img") else ""

            stream_link_el = card.find("a", href=True)
            stream_url = stream_link_el["href"] if stream_link_el else ""
            if stream_url and not stream_url.startswith("http"):
                stream_url = "https://footfytv.pro" + stream_url

            match_info = {
                "id": match_id,
                "title": f"{home_name} vs {away_name}",
                "home_team": {
                    "name": home_name,
                    "logo": home_logo
                },
                "away_team": {
                    "name": away_name,
                    "logo": away_logo
                },
                "stream_url": stream_url,
                "status": status
            }

            if "live" in status:
                matches_data["live"].append(match_info)
            elif "finish" in status or "ended" in status:
                matches_data["finished"].append(match_info)
            else:
                matches_data["upcoming"].append(match_info)

        except Exception as err:
            print(f"Error parsing card: {err}")
            continue

    return matches_data

def save_json(data):
    if not data:
        print("No data to save.")
        return
    
    filename = "matches.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"Successfully saved to {filename}")

if __name__ == "__main__":
    data = fetch_matches()
    save_json(data)
