import asyncio, os
from playwright.async_api import async_playwright

TARGETS = [
    ("02_sunnysky_komponentci", "https://www.komponentci.net/sunnysky-x4110s-400-kv-drone-motoru-pmu11857"),
    ("02_sunnysky_kirpilab", "https://kirpilab.com/sunnysky-x4110s-400-kv-drone-motoru"),
    ("02_sunnysky_voltaj", "https://www.voltaj.net/sunnysky-x4110s-400-kv-drone-motoru-pmu35516"),
    ("04_1355_komponentci", "https://www.komponentci.net/1355-karbon-fiber-drone-pervane-seti-cw-ccw-siyah-pmu11868"),
    ("05_imx219_robocombo_arducam", "https://www.robocombo.com/arducam-imx219-sabit-odaklama-kamera-modulu-nvidia-jetson-uyumlu-3147"),
    ("11_ubec_alibaba", "https://turkish.alibaba.com/product-detail/MATEK-Mateksys-UBEC-DUO-4A-5-1601135495487.html"),
    ("16_ov5640_samm", "https://market.samm.com/en/ov5640-kamera-karti-b-5mp-2592x1944-balikgozu-lens-1"),
]

OUT = "/home/ati/Attia-Pro/Projectos/Teknofest-enes-group/last report/screenshots"

async def snap(p, name, url):
    browser = await p.chromium.launch(headless=True)
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1366, "height": 900},
        locale="tr-TR",
    )
    page = await ctx.new_page()
    try:
        await page.goto(url, timeout=45000, wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)
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
