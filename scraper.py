import os
import json
import asyncio
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

TARGET_URL = "https://footfytv.pro/"

# যেসব টেক্সট থাকলে বুঝবো এগুলো কোনো ম্যাচের তথ্য নয় (অপ্রয়োজনীয় লিঙ্ক ফিল্টার)
EXCLUDE_KEYWORDS = [
    "privacy policy", "terms", "contact", "dmca", "home", "about",
    "facebook", "telegram", "twitter", "instagram", "copyright", "disclaimer"
]

async def extract_all_servers_from_match(page, match_url):
    """
    ম্যাচ পেজে ঢুকে সকল স্ট্রিমিং সার্ভার বাটন (Server 1, Server 2, M3U8)
    এবং iFrame ডিপ ড্রাইভ করে সকল স্ট্রিম লিঙ্ক বের করার ফাংশন
    """
    servers = []
    intercepted_m3u8s = []

    # Network Requests ইন্টারসেপ্ট করে m3u8 ক্যাপচার করা
    def handle_request(request):
        url = request.url
        if any(ext in url for ext in [".m3u8", "playlist.m3u8", "index.m3u8"]):
            if url not in intercepted_m3u8s:
                intercepted_m3u8s.append(url)

    page.on("request", handle_request)

    try:
        print(f"Deep driving into match page: {match_url}")
        await page.goto(match_url, wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_timeout(4000)

        # ১. পেজের সকল সার্ভার বাটন বা প্লেয়ার অপশন সিলেক্ট করা
        server_buttons = await page.query_selector_all("button, .server-btn, .tab-btn, a[class*='server'], a[href*='stream']")
        
        if server_buttons:
            for idx, btn in enumerate(server_buttons[:6]): # প্রথম ৫-৬টি প্রধান সার্ভার টেস্ট করা
                try:
                    btn_text = (await btn.inner_text()).strip() or f"Server {idx+1}"
                    await btn.click(timeout=2000)
                    await page.wait_for_timeout(1500)
                except Exception:
                    pass

        # ২. HTML ও Scripts থেকে লিঙ্ক এক্সট্র্যাক্ট করা
        content = await page.content()
        found_m3u8 = re.findall(r'(https?://[^\s\'"]+\.m3u8[^\s\'"]*)', content)
        
        # ৩. iFrames ডিপ ড্রাইভ (Embed Players)
        iframes = page.frames
        iframe_links = []
        for frame in iframes:
            try:
                frame_url = frame.url
                if frame_url and frame_url != "about:blank" and "google" not in frame_url:
                    iframe_links.append(frame_url)
                frame_content = await frame.content()
                f_m3u8 = re.findall(r'(https?://[^\s\'"]+\.m3u8[^\s\'"]*)', frame_content)
                found_m3u8.extend(f_m3u8)
            except Exception:
                continue

        # সকল প্রাপ্ত স্ট্রিম সার্ভার ফিল্টার ও ইউনিক রাখা
        all_unique_streams = list(dict.fromkeys(intercepted_m3u8s + found_m3u8 + iframe_links))

        for idx, stream_link in enumerate(all_unique_streams):
            name = f"Server {idx + 1}"
            if ".m3u8" in stream_link:
                name += " (Direct M3U8)"
            elif "embed" in stream_link or "iframe" in stream_link:
                name += " (Embed Player)"

            servers.append({
                "server_name": name,
                "stream_url": stream_link
            })

    except Exception as e:
        print(f"Error in deep driving {match_url}: {e}")

    # যদি কোনো নির্দিষ্ট সার্ভার না পাওয়া যায়, মূল ম্যাচ পেজকেই ডিফল্ট সার্ভার হিসেবে যোগ করবে
    if not servers:
        servers.append({
            "server_name": "Server 1 (Default)",
            "stream_url": match_url
        })

    return servers

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
            print("Loading FootfyTV Homepage...")
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(5000)

            # স্ক্রোল করে পেজ রেন্ডারিং নিশ্চিত করা
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            # ১. শুধুমাত্র কাজের ম্যাচ কার্ডগুলো ফিল্টার করা (অপ্রয়োজনীয় লিঙ্ক বাদ দেওয়া)
            valid_match_items = []
            cards = soup.find_all(["a", "div", "li"])

            for card in cards:
                text = card.get_text(separator=" ", strip=True)
                
                # অপ্রয়োজনীয় শব্দ বা খালি লিঙ্ক ফিল্টার
                if not text or len(text) < 4 or any(k in text.lower() for k in EXCLUDE_KEYWORDS):
                    continue

                # আসল লিঙ্ক বা ম্যাচ পাথ খুঁজে নেওয়া
                a_tag = card if card.name == "a" else card.find("a")
                if not a_tag or not a_tag.get("href"):
                    continue

                path = a_tag["href"]
                if path in ["#", "/", "javascript:void(0);"] or any(k in path.lower() for k in EXCLUDE_KEYWORDS):
                    continue

                full_match_url = path if path.startswith("http") else f"https://footfytv.pro{path if path.startswith('/') else '/' + path}"

                # টিম লোগো এক্সট্র্যাক্ট করা
                imgs = [img.get("src") or img.get("data-src") or "" for img in card.find_all("img")]
                logos = [img if img.startswith("http") else f"https://footfytv.pro{img}" for img in imgs if img]

                # ক্যাটাগরি এক্সট্র্যাক্ট করা
                category = "General Sports"
                parent = card.find_parent(["section", "div", "ul"])
                if parent:
                    cat_header = parent.find(["h1", "h2", "h3", "h4", "span"])
                    if cat_header:
                        cat_text = cat_header.get_text(strip=True)
                        if len(cat_text) < 30 and not any(k in cat_text.lower() for k in EXCLUDE_KEYWORDS):
                            category = cat_text

                # ডুপ্লিকেট রোধ
                if not any(m["match_page_url"] == full_match_url for m in valid_match_items):
                    match_id = card.get("id") or card.get("data-id") or full_match_url.rstrip("/").split("/")[-1]
                    
                    status = "upcoming"
                    if any(k in text.lower() for k in ["live", "1st half", "2nd half", "সরাসরি"]):
                        status = "live"
                    elif any(k in text.lower() for k in ["finished", "ended", "ft"]):
                        status = "finished"

                    valid_match_items.append({
                        "id": str(match_id),
                        "title": text,
                        "category": category,
                        "match_page_url": full_match_url,
                        "home_logo": logos[0] if len(logos) > 0 else "",
                        "away_logo": logos[1] if len(logos) > 1 else (logos[0] if len(logos) > 0 else ""),
                        "status": status
                    })

            print(f"Filtered {len(valid_match_items)} clean match items. Starting Deep Driving for Multi-Server Extraction...")

            # ২. প্রতিটি ফিল্টার হওয়া ম্যাচের ভেতরে ঢুকে একাধিক সার্ভার লিঙ্ক বের করা
            for match in valid_match_items:
                stream_servers = await extract_all_servers_from_match(page, match["match_page_url"])
                
                match_info = {
                    "id": match["id"],
                    "title": match["title"],
                    "category": match["category"],
                    "home_team": {"logo": match["home_logo"]},
                    "away_team": {"logo": match["away_logo"]},
                    "match_page_url": match["match_page_url"],
                    "servers": stream_servers, # একাধিক স্ট্রিমিং সার্ভার লিস্ট
                    "status": match["status"]
                }

                # ক্যাটাগরি অনুযায়ী গ্রুপ করা
                cat = match["category"]
                if cat not in matches_data["categories"]:
                    matches_data["categories"][cat] = []
                matches_data["categories"][cat].append(match_info)

                # স্ট্যাটাস অনুযায়ী লিস্টে রাখা
                if match["status"] == "live":
                    matches_data["live"].append(match_info)
                elif match["status"] == "finished":
                    matches_data["finished"].append(match_info)
                else:
                    matches_data["upcoming"].append(match_info)

        except Exception as e:
            print(f"Scraping error: {e}")
        finally:
            await browser.close()

    return matches_data

def save_json(data):
    with open("matches.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print("matches.json saved with cleaned data & multi-server links!")

if __name__ == "__main__":
    data = asyncio.run(run_deep_scraper())
    save_json(data)
