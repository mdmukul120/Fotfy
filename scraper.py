import os
import json
import asyncio
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

TARGET_URL = "https://footfytv.pro/"

async def fetch_matches():
    current_utc_time = datetime.now(timezone.utc).isoformat()
    
    matches_data = {
        "last_updated_utc": current_utc_time,
        "live": [],
        "upcoming": [],
        "finished": []
    }

    async with async_playwright() as p:
        # Chromium Headless Browser চালু করা হচ্ছে Anti-Bot bypassing সহ
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        page = await context.new_page()

        try:
            print("Loading page via Playwright...")
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
            
            # JavaScript রেন্ডার সম্পূর্ণ হওয়ার জন্য ৫ সেকেন্ড অপেক্ষা
            await page.wait_for_timeout(5000)

            # পেজের ফুল রেন্ডার্ড HTML সংগ্রহ
            html_content = await page.content()
            await browser.close()

        except Exception as e:
            print(f"Error loading page with Playwright: {e}")
            await browser.close()
            return matches_data

    # BeautifulSoup দিয়ে পার্স করা
    soup = BeautifulSoup(html_content, "html.parser")
    
    # ফুটফাই টিভির ম্যাচ ব্লক বা লিংক সিলেক্টর (সামগ্রিক স্ট্রাকচার খোঁজা)
    cards = soup.select("a[href*='match'], .match-card, .event-item, div[class*='match'], div[class*='event']")

    for card in cards:
        try:
            text_content = card.text.strip()
            if not text_content:
                continue

            # Stream Link 추출
            href = card.get("href") or ""
            if href and not href.startswith("http"):
                stream_url = "https://footfytv.pro" + href
            else:
                stream_url = href

            # Logos 추출
            imgs = card.find_all("img")
            home_logo = imgs[0]["src"] if len(imgs) > 0 and imgs[0].has_attr("src") else ""
            away_logo = imgs[1]["src"] if len(imgs) > 1 and imgs[1].has_attr("src") else ""

            # ID Extraction
            match_id = card.get("id") or card.get("data-id") or href.split("/")[-1] or "N/A"

            # Match Info Map
            match_info = {
                "id": match_id,
                "title": text_content.replace("\n", " "),
                "home_team": {"name": "Home", "logo": home_logo},
                "away_team": {"name": "Away", "logo": away_logo},
                "stream_url": stream_url,
                "status": "live" if "live" in text_content.lower() else "upcoming"
            }

            if "live" in text_content.lower():
                matches_data["live"].append(match_info)
            elif "ended" in text_content.lower() or "ft" in text_content.lower():
                matches_data["finished"].append(match_info)
            else:
                matches_data["upcoming"].append(match_info)

        except Exception as err:
            continue

    return matches_data

def save_json(data):
    with open("matches.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print("matches.json updated successfully!")

if __name__ == "__main__":
    data = asyncio.run(fetch_matches())
    save_json(data)
