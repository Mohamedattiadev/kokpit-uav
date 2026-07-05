"""ArUco marker tespit — yaklaşma geometrisi ve görüntü bozulma sweep'i.

Literatür bulguları (bkz. NEXT_SESSION araştırma notları):
  * Min. kod bölgesi piksel boyu ~12-32px altında tespit güvenilmez.
  * Motion blur, gerçek zamanlı tespit hatasının başlıca nedenlerinden biri.
  * Küçük kenar okluzyonu tolere edilebilir, büyük okluzyon tespiti bozar.
  * Oblique açılar orta dereceye kadar (kod hâlâ ayırt edilebilirken) tespit
    edilebilir; ChArUco rehberleri "extreme angles" ile çeşitlilik önerir.

Bu testler onboard/aruco_detector.py'yi (GERÇEK tespit/poz kestirim kodu),
simulation/sim_backend.SimDownCamera'nın yeni bozulma enjeksiyon
parametreleriyle (oblique_deg, occlusion_frac, brightness, motion_blur_px)
sistematik bir açı/irtifa/hız ızgarasında sınar."""
from __future__ import annotations
import pytest

from config import CFG
from aruco_detector import ArucoDetector
from sim_backend import FakeDrone, SimDownCamera


def _make_camera(alt_rel=6.0, heading=0.0, marker_len=0.5):
    drone = FakeDrone(home_lat=39.942000, home_lon=32.847000)
    drone.alt = alt_rel
    drone.heading = heading
    mlat, mlon = drone.home_lat, drone.home_lon   # tam altında (offset yok)
    cam = SimDownCamera(drone, mlat, mlon, marker_len_m=marker_len)
    return drone, cam


@pytest.mark.parametrize("alt_rel", [2.0, 6.0, 10.0, 15.0])
def test_altitude_vs_pixel_size_detection_boundary(alt_rel):
    """Rapor: search_altitude_m=10, approach_altitude_m=6, drop_altitude_m=2.5.
    Bu irtifa aralığında (0.5 m marker) tespit başarılı olmalı; irtifa arttıkça
    kod piksel boyu küçülür ama 15 m'de bile (rapor cruise=15m) hâlâ min.
    piksel eşiğinin üzerinde kalmalı (aksi halde hedefe varışta marker asla
    görünmez)."""
    drone, cam = _make_camera(alt_rel=alt_rel)
    det = ArucoDetector()
    ok, frame = cam.read()
    d = det.detect(frame)
    assert d.found, f"irtifa {alt_rel}m'de marker tespit edilemedi (min piksel sınırı?)"


@pytest.mark.parametrize("oblique_deg", [0, 15, 30, 45, 60, 75])
def test_oblique_approach_angle_sweep(oblique_deg):
    """0-75° arası yaklaşma/eğim açısı sweep'i. Literatür: orta açılara kadar
    (~60°) tespit güvenilir kalmalı; 75° gibi çok yatık açılarda (kod bölgesi
    aşırı sıkışmış) tespitin bozulması BEKLENEN bir davranıştır — bu test
    beklenen sınırı belgeler, hepsi PASS olmalı diye zorlamaz."""
    drone, cam = _make_camera(alt_rel=5.0)
    cam.oblique_deg = oblique_deg
    det = ArucoDetector()
    ok, frame = cam.read()
    d = det.detect(frame)
    if oblique_deg <= 45:
        assert d.found, f"{oblique_deg}° gibi orta açıda hâlâ tespit edilmeli"
    # 60°+ için tespit garantisi yok (literatürle uyumlu bilinen sınır) —
    # sadece crash/exception olmadığını doğruluyoruz (üstteki detect() çağrısı
    # zaten bunu kanıtlar).


@pytest.mark.parametrize("occlusion_frac", [0.0, 0.10, 0.15, 0.30, 0.50])
def test_partial_occlusion_tolerance(occlusion_frac):
    """BULGU: bir köşeyi kapatan okluzyon, OpenCV'nin ArUco tespit algoritması
    için beklenenden daha kırılgan — algoritma dış kare konturunun TAMAMINI
    kapalı bir dörtgen olarak bulmayı gerektirdiğinden, tek bir köşenin
    kapanması (%15+) tüm marker'ı 'bulunamadı' yapabiliyor (kod bölgesindeki
    kısmi okluzyon toleransıyla KARIŞTIRILMAMALI — kenar/köşe okluzyonu çok
    daha az tolere ediliyor). Yalnızca çok küçük (%10) köşe okluzyonu güvenilir
    kalıyor; %15 ve üzeri için tespit garantisi YOK. Bu, saha pedinin
    üzerine drone gövde gölgesi/anten düşme riskine karşı ped tasarımı için
    (marker'ın kenarlarında geniş boşluk bırakma) bir öneri olarak rapora
    not edildi."""
    drone, cam = _make_camera(alt_rel=4.0)
    cam.occlusion_frac = occlusion_frac
    det = ArucoDetector()
    ok, frame = cam.read()
    d = det.detect(frame)
    if occlusion_frac <= 0.10:
        assert d.found, f"%{occlusion_frac*100:.0f} okluzyonda hâlâ tespit edilmeli"


@pytest.mark.parametrize("brightness", [0.15, 0.4, 1.0, 1.8, 3.0])
def test_lighting_extremes_low_light_and_glare(brightness):
    """Düşük ışık (backlit/gölge, brightness<0.4) ve aşırı parlaklık/glare
    (brightness>1.8) senaryoları — nominal (1.0) her zaman tespit etmeli;
    uçlarda tespitin bozulması kabul edilir ama crash/exception OLMAMALI."""
    drone, cam = _make_camera(alt_rel=4.0)
    cam.brightness = brightness
    det = ArucoDetector()
    ok, frame = cam.read()
    d = det.detect(frame)   # crash etmemeli
    if brightness == 1.0:
        assert d.found


@pytest.mark.parametrize("blur_px", [0, 5, 15, 31])
def test_motion_blur_at_speed_sweep(blur_px):
    """Yatay hareket bulanıklığı sweep'i (yavaş=0px .. hızlı geçiş=31px).
    Literatür: yüksek hızda motion blur ArUco tespitinin başlıca gerçek
    zamanlı hata nedenlerinden biri — bu sweep, hassas yaklaşma sırasında
    max_xy_speed_ms (1.5 m/s) gibi düşük hızların neden tercih edildiğini
    doğrular (blur=0'da tespit başarılı, yüksek blur'da bozulma beklenir)."""
    drone, cam = _make_camera(alt_rel=4.0)
    cam.motion_blur_px = blur_px
    det = ArucoDetector()
    ok, frame = cam.read()
    d = det.detect(frame)
    if blur_px == 0:
        assert d.found


def test_marker_too_small_beyond_search_altitude_correctly_not_found():
    """search_altitude_m'nin çok üzerinde (örn. cruise 15m + marka 0.3m küçük
    marker) kod piksel boyu min. eşiğin (14px) altına düşerse detector
    False dönmeli — SimDownCamera zaten bunu code_px<14 kontrolüyle modelliyor;
    burada ArucoDetector'ın da tutarlı bir 'found=False' ürettiğini (crash
    değil) doğruluyoruz."""
    drone, cam = _make_camera(alt_rel=40.0, marker_len=0.15)
    det = ArucoDetector()
    ok, frame = cam.read()
    d = det.detect(frame)
    assert not d.found
