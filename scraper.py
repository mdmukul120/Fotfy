import json
import asyncio
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

TARGET_URL = "https://footfytv.pro/"

async def fetch_matches_advanced():
    current_utc_time = datetime.now(timezone.utc).isoformat()
    
    matches_data = {
        "last_updated_utc": current_utc_time,
        "live": [],
        "upcoming": [],
        "finished": []
    }

    captured_json_responses = []

    async with async_playwright() as p:
        # Launch Chromium with Stealth & Anti-bot Bypassing configurations
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US"
        )

        page = await context.new_page()

        # Stealth Override
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        # Network Request Interception to Capture Dynamic JSON/API Responses
        async def handle_response(response):
            if "api" in response.url or "json" in response.url or "matches" in response.url or "events" in response.url:
                try:
                    if response.status == 200 and "application/json" in response.headers.get("content-type", ""):
                        json_data = await response.json()
                        captured_json_responses.append(json_data)
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            print("Navigating to FootfyTV with Advanced Interceptor...")
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            
            # Wait for JS and Cloudflare checks to pass
            await page.wait_for_timeout(8000)

            # Auto Scroll to trigger Lazy Loading items
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3000)

            html_content = await page.content()

        except Exception as e:
            print(f"Error loading page: {e}")
        finally:
            await browser.close()

    # Step 1: Process Intercepted API Data if Captured
    if captured_json_responses:
        print("Successfully Intercepted API Network Responses!")
        for res in captured_json_responses:
            # Flexible parsing logic depending on API response structure
            items = res if isinstance(res, list) else res.get("data") or res.get("matches") or []
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        match_info = {
                            "id": str(item.get("id") or item.get("match_id") or "N/A"),
                            "title": item.get("title") or f"{item.get('home_name', '')} vs {item.get('away_name', '')}",
                            "home_team": {
                                "name": item.get("home_team") or item.get("home_name") or "Home",
                                "logo": item.get("home_logo") or item.get("home_icon") or ""
                            },
                            "away_team": {
                                "name": item.get("away_team") or item.get("away_name") or "Away",
                                "logo": item.get("away_logo") or item.get("away_icon") or ""
                            },
                            "stream_url": item.get("stream_url") or item.get("link") or item.get("url") or TARGET_URL,
                            "status": str(item.get("status", "")).lower()
                        }
                        
                        if "live" in match_info["status"] or item.get("is_live"):
                            matches_data["live"].append(match_info)
                        elif "finish" in match_info["status"] or "ended" in match_info["status"]:
                            matches_data["finished"].append(match_info)
                        else:
                            matches_data["upcoming"].append(match_info)

    # Step 2: Fallback Deep DOM Parsing if API direct intercept was blocked
    if not matches_data["live"] and not matches_data["upcoming"]:
        print("Fallback to Deep DOM Scrape...")
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Generic Deep Selector for Football Streaming Sites (A, DIV, LI Containers)
        elements = soup.find_all(["a", "div", "li"], class_=True)
        for el in elements:
            class_str = " ".join(el.get("class", [])).lower()
            if any(k in class_str for k in ["match", "game", "event", "item", "stream", "card"]):
                text = el.get_text(separator=" ", strip=True)
                if "vs" in text.lower() or " - " in text:
                    href = el.get("href") if el.name == "a" else (el.find("a")["href"] if el.find("a") else "")
                    if href and not href.startswith("http"):
                        href = "https://footfytv.pro" + href

                    imgs = [img["src"] for img in el.find_all("img") if img.get("src")]
                    
                    match_info = {
                        "id": el.get("id") or el.get("data-id") or "N/A",
                        "title": text,
                        "home_team": {"name": "Home", "logo": imgs[0] if len(imgs) > 0 else ""},
                        "away_team": {"name": "Away", "logo": imgs[1] if len(imgs) > 1 else ""},
                        "stream_url": href or TARGET_URL,
                        "status": "live" if "live" in text.lower() else "upcoming"
                    }
                    
                    if "live" in text.lower():
                        matches_data["live"].append(match_info)
                    else:
                        matches_data["upcoming"].append(match_info)

    return matches_data

def save_json(data):
    with open("matches.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print("matches.json saved successfully!")

if __name__ == "__main__":
    data = asyncio.run(fetch_matches_advanced())
    save_json(data)
