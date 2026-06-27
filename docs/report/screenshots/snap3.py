import asyncio, os
from playwright.async_api import async_playwright

TARGETS = [
    ("02_sunnysky_amazon", "https://www.amazon.com.tr/s?k=sunnysky+x4110s+400kv"),
    ("04_1355_amazon", "https://www.amazon.com.tr/s?k=1355+karbon+pervane+cw+ccw"),
    ("05_imx219_amazon", "https://www.amazon.com.tr/s?k=IMX219-160+waveshare"),
    ("11_ubec_amazon", "https://www.amazon.com.tr/s?k=matek+ubec+duo"),
    ("02_sunnysky_robotzade", "https://www.robotzade.com/sunnysky-x4110s-400-kv,TA-10518.html"),
    ("04_1355_robotzade", "https://www.robotzade.com/1355-karbon-fiber-drone-pervane,TA-13488.html"),
    ("11_ubec_robotzade", "https://www.robotzade.com/matek-ubec-duo,TA-9999.html"),
    ("11_ubec_hipodrone", "https://www.hipodrone.com.tr/kategori/guc-dagitim-bec"),
    ("02_sunnysky_robocombo_search", "https://www.robocombo.com/arama?q=sunnysky+x4110s"),
    ("04_1355_robocombo_search", "https://www.robocombo.com/arama?q=1355"),
]

OUT = "/home/ati/Attia-Pro/Projectos/Teknofest-enes-group/last report/screenshots"

async def snap(p, name, url):
    browser = await p.chromium.launch(headless=True)
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1366, "height": 1400},
        locale="tr-TR",
    )
    page = await ctx.new_page()
    try:
        await page.goto(url, timeout=45000, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        path = os.path.join(OUT, f"{name}.png")
        await page.screenshot(path=path, full_page=False)
        print(f"OK {name}")
    except Exception as e:
        print(f"FAIL {name}: {e}")
    finally:
        await browser.close()

async def main():
    async with async_playwright() as p:
        for name, url in TARGETS:
            await snap(p, name, url)

asyncio.run(main())
