import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print("Navigating...")
        await page.goto('https://reanime.to/search?keyword=bleach')
        print("Waiting...")
        await page.wait_for_timeout(5000)
        html = await page.content()
        print('bleach in HTML:', 'bleach' in html.lower())
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
