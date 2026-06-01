import asyncio
from playwright.async_api import async_playwright

async def test_shiroko():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print("Navigating to Shiroko search...")
        await page.goto("https://shiroko.co/search?q=naruto")
        
        try:
            print("Waiting for watch links...")
            await page.wait_for_selector('a[href^="/watch"]', timeout=5000)
        except Exception as e:
            print(f"Error waiting for selector: {e}")
            
        html = await page.content()
        import re
        urls = re.findall(r'href=[\"\'\\]+?([^\"\'\\]+)', html)
        watch_urls = [u for u in urls if u.startswith("/watch")]
        print("Found watch URLs:", watch_urls[:5])
        
        await browser.close()

asyncio.run(test_shiroko())
