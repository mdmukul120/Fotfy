import os
import re
import json
import asyncio
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright

BASE_URL = "https://fs.plus.net.bd/"

# যেসব এক্সটেনশন থাকলে বুঝব এগুলো মিডিয়া ফাইল (Direct Media Links)
MEDIA_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.webm', '.m4v', '.mov', '.iso')

# যেসব ফাইল/লিঙ্ক স্কিপ করা হবে (Junk / Non-media filtering)
EXCLUDE_EXTENSIONS = ('.srt', '.sub', '.txt', '.nfo', '.jpg', '.png', '.jpeg', '.pdf', '.zip', '.rar', '.exe', '.css', '.js','.apk')
EXCLUDE_KEYWORDS = ['login', 'signup', 'register', 'contact', 'about', 'privacy', 'terms', 'dmca', 'faq', 'logout']

# ডাটা সংরক্ষণের স্ট্রাকচার
scraped_data = {
    "base_url": BASE_URL,
    "movies": [],
    "web_series": [],
    "other_content": []
}

visited_urls = set()

def categorize_item(title, url):
    """
    টাইটেল বা ইউআরএল দেখে ক্যাটাগরি (Movie vs Web Series) নির্ধারণ
    """
    lower_text = f"{title} {url}".lower()
    
    # Season / Episode / S01E01 নির্দেশক থাকলে তা Web Series
    if re.search(r'\bs\d{1,2}\b|\be\d{1,2}\b|season|episode|ep\s*\d+|s01|s02|s03', lower_text):
        return "web_series"
    elif any(k in lower_text for k in ['tv series', 'series', 'webseries', 'drama', 'shows']):
        return "web_series"
    else:
        return "movies"

def is_valid_url(url):
    """ইউআরএল ভ্যালিডেশন এবং বাইরের ডোমেইন ফিল্টার"""
    parsed_base = urlparse(BASE_URL)
    parsed_url = urlparse(url)
    
    if parsed_url.netloc and parsed_url.netloc != parsed_base.netloc:
        return False
        
    path = parsed_url.path.lower()
    if any(path.endswith(ext) for ext in EXCLUDE_EXTENSIONS):
        return False
        
    if any(k in path for k in EXCLUDE_KEYWORDS):
        return False
        
    return True

async def deep_crawl(page, current_url, depth=0, max_depth=5):
    """
    ওয়েব লিঙ্কের ভেতরে ডিপ ড্রাইভ করে সকল MP4/MKV এবং ইমেজ বের করার রিকার্সিভ ফাংশন
    """
    if depth > max_depth or current_url in visited_urls:
        return

    visited_urls.add(current_url)
    print(f"[Depth {depth}] Crawling: {current_url}")

    try:
        await page.goto(current_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1000)

        # ১. সরাসরি ভিডিও ফাইলের লিঙ্ক চেক
        if current_url.lower().endswith(MEDIA_EXTENSIONS):
            category = categorize_item(os.path.basename(current_url), current_url)
            item = {
                "title": os.path.basename(current_url),
                "media_link": current_url,
                "image": "",
                "category": category,
                "source_page": current_url
            }
            scraped_data[category].append(item)
            return

        # ২. বর্তমান পেজের সকল Links, Images, and Embeds বের করা
        elements = await page.query_selector_all("a, img, source, video")
        
        page_images = []
        page_media_links = []
        sub_directories = []

        for elem in elements:
            tag_name = await elem.evaluate("el => el.tagName.toLowerCase()")
            
            if tag_name == "img":
                src = await elem.get_attribute("src") or await elem.get_attribute("data-src")
                if src:
                    full_img_url = urljoin(current_url, src)
                    if not full_img_url.endswith(('.ico', '.svg')):
                        page_images.append(full_img_url)

            elif tag_name == "a":
                href = await elem.get_attribute("href")
                text = (await elem.inner_text()).strip()
                
                if not href or href in ["#", "/", "javascript:void(0);"]:
                    continue
                
                full_href = urljoin(current_url, href)

                if not is_valid_url(full_href):
                    continue

                # মিডিয়া ফাইল (MP4, MKV) পাওয়া গেলে
                if full_href.lower().endswith(MEDIA_EXTENSIONS):
                    page_media_links.append({
                        "title": text or os.path.basename(full_href),
                        "url": full_href
                    })
                # সাব-ডিরেক্টরি বা পরবর্তী স্লগ ইউআরএল হলে (ডিপ ড্রাইভের জন্য)
                elif full_href not in visited_urls:
                    sub_directories.append(full_href)

            elif tag_name in ["source", "video"]:
                src = await elem.get_attribute("src")
                if src and src.lower().endswith(MEDIA_EXTENSIONS):
                    page_media_links.append({
                        "title": os.path.basename(src),
                        "url": urljoin(current_url, src)
                    })

        # ৩. যদি বর্তমান পেজে মিডিয়া লিঙ্ক পাওয়া যায়, তবে তা অবজেক্ট আকারে সেভ করা
        primary_image = page_images[0] if page_images else ""

        for media in page_media_links:
            cat = categorize_item(media["title"], media["url"])
            item_entry = {
                "title": media["title"],
                "category": cat,
                "media_url": media["url"],
                "poster_image": primary_image,
                "slug_url": current_url
            }
            scraped_data[cat].append(item_entry)

        # ৪. সাব-ডিরেক্টরি / স্লগ ইউআরএলগুলোতে ডিপ ড্রাইভ (Deep Drive) করা
        for next_url in sub_directories:
            await deep_crawl(page, next_url, depth + 1, max_depth)

    except Exception as e:
        print(f"Error crawling {current_url}: {e}")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print(f"Starting Deep Drive Scraper for: {BASE_URL}")
        await deep_crawl(page, BASE_URL, depth=0, max_depth=6)

        # ফিল্টারিং ডুপ্লিকেট আইটেম
        for cat in ["movies", "web_series"]:
            unique_items = []
            seen_urls = set()
            for item in scraped_data[cat]:
                if item["media_url"] not in seen_urls:
                    seen_urls.add(item["media_url"])
                    unique_items.append(item)
            scraped_data[cat] = unique_items

        # JSON ফাইলে ফলাফল সেভ করা
        with open("fs_plus_media_data.json", "w", encoding="utf-8") as f:
            json.dump(scraped_data, f, ensure_ascii=False, indent=4)

        print("\nScraping Completed Successfully!")
        print(f"Total Movies Found: {len(scraped_data['movies'])}")
        print(f"Total Web Series Episodes Found: {len(scraped_data['web_series'])}")
        print("Data saved into 'fs_plus_media_data.json'")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
