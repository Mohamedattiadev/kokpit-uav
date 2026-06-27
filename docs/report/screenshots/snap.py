import asyncio, os
from playwright.async_api import async_playwright

TARGETS = [
    ("02_sunnysky_trendyol", "https://trendyol.com/sunnysky/kv-drone-motoru-x4110s-400-p-72407241"),
    ("04_1355_n11_search", "https://www.n11.com/arama?q=1355+karbon+pervane"),
    ("05_imx219_hepsiburada", "https://www.hepsiburada.com/waveshare-imx219-kamera-modulu-160-derece-gorus-acisi-pm-HBC000056FAKL"),
    ("06_jetson_openzeka", "https://openzeka.com/urun/nvidia-jetson-orin-nano-developer-kit/"),
    ("07_m9n_dronenettr", "https://drone.net.tr/en/drone-tuning/holybro-holybro-m9n-gps-for-pix32-2-4-6.html"),
    ("08_tfmini_dronenettr", "https://drone.net.tr/en/gimbal-ve-faydali-yukler/tfmini-s-12m-lidar-ranging-module.html"),
    ("11_ubec_n11", "https://www.n11.com/urun/matek-ubec-duo-4a512v-4a5v-bec-regulator-5379901"),
    ("16_ov5640_trendyol", "https://www.trendyol.com/waveshare/ov5640-kamera-karti-c-5mp-2592x1944-otomatik-odaklama-dahili-flas-p-769548313"),
    ("16_ov5640_hepsiburada", "https://www.hepsiburada.com/pabiflo-hd-usb-kamera-modulu-ov5640-5mp-25921944p-otomatik-odaklama-otg-uvc-usb-kamera-modulu-android-windows-linux-icin-yurt-disindan-pm-HBC00005Y63K7"),
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
        await page.screenshot(path=path, full_page=True)
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
