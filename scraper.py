import os
import json
import asyncio
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

TARGET_URL = "https://footfytv.pro/"

async def scrape_footfy_matches():
    current_utc_time = datetime.now(timezone.utc).isoformat()
    
    output_data = {
        "last_updated_utc": current_utc_time,
        "categories": {}, # ক্যাটাগরি অনুযায়ী ম্যাচ
        "live": [],
        "upcoming": [],
        "finished": []
    }

    async with async_playwright() as p:
        print("Launching Stealth Browser...")
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        page = await context.new_page()

        try:
            print("Navigating to FootfyTV...")
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
            
            # ডাইনামিক ডেটা এবং লোগো লোড হওয়ার জন্য সময় দেওয়া
            await page.wait_for_timeout(8000)

            # পেজের একদম নিচে স্ক্রোল করে পুরো কন্টেন্ট ট্র্রিগার করা
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3000)

            # মূল পেজের সম্পূর্ণ রেন্ডার হওয়া HTML সংগ্রহ
            html_content = await page.content()

        except Exception as e:
            print(f"Error loading page: {e}")
            await browser.close()
            return output_data

        await browser.close()

    soup = BeautifulSoup(html_content, "html.parser")

    # সকল লিঙ্ক/কার্ড বিশ্লেষণ
    match_elements = soup.find_all(["a", "div", "li"])

    for el in match_elements:
        try:
            # লোগো বা ছবি সার্চ (অ্যাট্রিবিউট বা data-src সহ)
            imgs = el.find_all("img")
            logos = []
            for img in imgs:
                src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
                if src:
                    if not src.startswith("http"):
                        src = "https://footfytv.pro" + (src if src.startswith("/") else "/" + src)
                    logos.append(src)

            # স্ট্রিমিং ইউআরএল (href)
            stream_url = ""
            if el.name == "a" and el.get("href"):
                stream_url = el.get("href")
            else:
                a_tag = el.find("a", href=True)
                if a_tag:
                    stream_url = a_tag["href"]

            if stream_url and not stream_url.startswith("http"):
                stream_url = "https://footfytv.pro" + (stream_url if stream_url.startswith("/") else "/" + stream_url)

            # ম্যাচ টাইটেল ও টেক্সট
            text_content = el.get_text(separator=" ", strip=True)
            
            # লোগো এবং স্ট্রিম ইউআরএল না থাকলে এটি স্কিপ করবে
            if not stream_url or len(text_content) < 3:
                continue

            # ক্যাটাগরি ডিটেকশন (parent/section চেক)
            category = "General"
            parent = el.find_parent(["section", "div", "ul"])
            if parent:
                header = parent.find(["h1", "h2", "h3", "h4", "span", "div"], class_=lambda c: c and any(x in str(c).lower() for x in ["cat", "league", "title", "sport"]))
                if header:
                    category = header.get_text(strip=True)

            # টিম নাম ও আইডি এক্সট্রাকশন
            match_id = el.get("id") or el.get("data-id") or stream_url.split("/")[-1] or "N/A"
            
            status = "upcoming"
            if any(k in text_content.lower() for k in ["live", "সরাসরি", "1st half", "2nd half"]):
                status = "live"
            elif any(k in text_content.lower() for k in ["finished", "ended", "ft"]):
                status = "finished"

            match_info = {
                "id": match_id,
                "title": text_content,
                "category": category,
                "home_team": {
                    "logo": logos[0] if len(logos) > 0 else ""
                },
                "away_team": {
                    "logo": logos[1] if len(logos) > 1 else (logos[0] if len(logos) > 0 else "")
                },
                "stream_url": stream_url,
                "status": status
            }

            # ক্যাটাগরি ভিত্তিক গ্রুপ করা
            if category not in output_data["categories"]:
                output_data["categories"][category] = []
            
            # ডুপ্লিকেট রিমুভ করে যুক্ত করা
            if not any(m["stream_url"] == stream_url for m in output_data["categories"][category]):
                output_data["categories"][category].append(match_info)

            # মেইন স্ট্যাটাস লিস্টে যুক্ত করা
            if status == "live":
                output_data["live"].append(match_info)
            elif status == "finished":
                output_data["finished"].append(match_info)
            else:
                output_data["upcoming"].append(match_info)

        except Exception:
            continue

    return output_data

def save_json(data):
    filename = "matches.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"{filename} successfully generated!")

if __name__ == "__main__":
    data = asyncio.run(scrape_footfy_matches())
    save_json(data)
