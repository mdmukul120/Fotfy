import os
import json
import asyncio
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

TARGET_URL = "https://footfytv.pro/"

async def extract_m3u8_from_page(page, match_url):
    """
    প্রতিটি ম্যাচের পেজের ভেতরে ঢুকে .m3u8 লিঙ্ক এবং আইফ্রেম ডিপ ড্রাইভিং করার ফাংশন
    """
    m3u8_links = []

    # Network Request Interceptor for capturing live .m3u8 streams directly
    def handle_request(request):
        url = request.url
        if ".m3u8" in url or "index.m3u8" in url or "playlist.m3u8" in url:
            if url not in m3u8_links:
                m3u8_links.append(url)

    page.on("request", handle_request)

    try:
        print(f"Deep driving into match: {match_url}")
        await page.goto(match_url, wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_timeout(4000)

        # ১. যদি নেটওয়ার্ক রিকোয়েস্টে সরাসরি m3u8 পাওয়া যায়
        if m3u8_links:
            return m3u8_links[0]

        # ২. HTML এবং Scripts এর ভেতরে Regex দিয়ে .m3u8 সার্চ করা
        content = await page.content()
        regex_matches = re.findall(r'(https?://[^\s\'"]+\.m3u8[^\s\'"]*)', content)
        if regex_matches:
            return regex_matches[0]

        # ৩. iFrame এর ভেতরে ডিপ ড্রাইভ করা (Player Embeds)
        iframes = page.frames
        for frame in iframes:
            try:
                frame_content = await frame.content()
                iframe_m3u8 = re.findall(r'(https?://[^\s\'"]+\.m3u8[^\s\'"]*)', frame_content)
                if iframe_m3u8:
                    return iframe_m3u8[0]
            except Exception:
                continue

    except Exception as e:
        print(f"Error fetching deep stream for {match_url}: {e}")

    return match_url # m3u8 না পাওয়া গেলে ডিফল্ট ম্যাচ ইউআরএল রাখবে

async def run_deep_scraper():
    current_utc_time = datetime.now(timezone.utc).isoformat()
    
    matches_data = {
        "last_updated_utc": current_utc_time,
        "categories": {},
        "live": [],
        "upcoming": [],
        "finished": []
    }

    async with async_playwright() as p:
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
            print("Fetching homepage match paths...")
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(5000)

            # স্ক্রোল করে সব ডায়নামিক ম্যাচ কার্ড ভিজিবল করা
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            # ১. পেজ থেকে সব ম্যাচের পাথ (Path/URLs) বের করা
            match_nodes = soup.find_all(["a", "div", "li"])
            extracted_matches = []

            for el in match_nodes:
                text = el.get_text(separator=" ", strip=True)
                
                # হাইপারলিঙ্ক সন্ধান
                a_tag = el if el.name == "a" else el.find("a")
                if not a_tag or not a_tag.get("href"):
                    continue

                path = a_tag["href"]
                if not path.startswith("http"):
                    match_page_url = "https://footfytv.pro" + (path if path.startswith("/") else "/" + path)
                else:
                    match_page_url = path

                # লোগো বের করা
                imgs = [img.get("src") or img.get("data-src") or "" for img in el.find_all("img")]
                logos = [img if img.startswith("http") else f"https://footfytv.pro{img}" for img in imgs if img]

                # ক্যাটাগরি এক্সট্র্যাক্ট করা
                category = "General"
                parent = el.find_parent(["section", "div", "ul"])
                if parent:
                    cat_el = parent.find(["h1", "h2", "h3", "h4", "span"])
                    if cat_el:
                        category = cat_el.get_text(strip=True)

                match_id = el.get("id") or el.get("data-id") or path.split("/")[-1] or "N/A"

                if match_page_url not in [m["page_url"] for m in extracted_matches] and len(text) > 2:
                    extracted_matches.append({
                        "id": match_id,
                        "title": text,
                        "category": category,
                        "page_url": match_page_url,
                        "home_logo": logos[0] if len(logos) > 0 else "",
                        "away_logo": logos[1] if len(logos) > 1 else (logos[0] if len(logos) > 0 else ""),
                        "status": "live" if "live" in text.lower() else ("finished" if "ft" in text.lower() else "upcoming")
                    })

            print(f"Total {len(extracted_matches)} match paths found. Starting deep m3u8 crawl...")

            # ২. প্রতিটি লিঙ্ক পাথে ড্রাইভ করে .m3u8 স্ট্রিম ইউআরএল সংগ্রহ করা
            for match in extracted_matches:
                # ডিপ পেজে ঢুকবে
                stream_m3u8 = await extract_m3u8_from_page(page, match["page_url"])
                
                match_info = {
                    "id": match["id"],
                    "title": match["title"],
                    "category": match["category"],
                    "home_team": {"logo": match["home_logo"]},
                    "away_team": {"logo": match["away_logo"]},
                    "match_page_url": match["page_url"],
                    "stream_m3u8_url": stream_m3u8,
                    "status": match["status"]
                }

                # ক্যাটাগরি অনুসারে সেভ করা
                cat = match["category"]
                if cat not in matches_data["categories"]:
                    matches_data["categories"][cat] = []
                matches_data["categories"][cat].append(match_info)

                # স্ট্যাটাস অনুসারে সেভ করা
                if match["status"] == "live":
                    matches_data["live"].append(match_info)
                elif match["status"] == "finished":
                    matches_data["finished"].append(match_info)
                else:
                    matches_data["upcoming"].append(match_info)

        except Exception as e:
            print(f"Error in deep scraping: {e}")
        finally:
            await browser.close()

    return matches_data

def save_json(data):
    with open("matches.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print("matches.json created with Deep m3u8 Links!")

if __name__ == "__main__":
    data = asyncio.run(run_deep_scraper())
    save_json(data)
