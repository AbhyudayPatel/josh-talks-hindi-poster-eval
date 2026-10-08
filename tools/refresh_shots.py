"""Rebuild the rating app and re-capture every UI screenshot used in the submission."""
import subprocess, sys, tempfile, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from shot import EDGE

subprocess.run([sys.executable, str(ROOT / "q1" / "build_rating_app.py"), "--allow-missing"], check=True)
app = ROOT / "q1" / "rating_app" / ("rate.html" if (ROOT / "q1" / "rating_app" / "rate.html").exists() and
                                     not list((ROOT / "q1" / "images").glob("*_g25.png")) == [] else "rate_PREVIEW.html")
src = app.read_text(encoding="utf-8")
demo = src.replace('let S = JSON.parse(localStorage.getItem("posterEval_" + BUILD) || "null") ||',
                   'let S = (()=>{const p={name:"Demo",email:"demo@x.com",pid:"R000000"};return {step:"rate",p,order:buildOrder(p.email),i:3,answers:{},t0:Date.now()};})() ||')
(ROOT / "work" / "demo_rate.html").write_text(demo, encoding="utf-8")
out = ROOT / "work" / "shots"; out.mkdir(parents=True, exist_ok=True)


def shot(url, png, w, h):
    with tempfile.TemporaryDirectory() as prof:
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={prof}",
                        f"--window-size={w},{h}", "--virtual-time-budget=3000", f"--screenshot={png}", url],
                       check=True, capture_output=True, timeout=180)


shot((ROOT / "work" / "demo_rate.html").as_uri(), out / "ui_rate.png", 1400, 1330)
base = (ROOT / "q1" / "mockups" / "product.html").as_uri()
subprocess.run([sys.executable, str(ROOT / "q1" / "mockups" / "build_leaderboard.py")], check=True)
subprocess.run([sys.executable, str(ROOT / "q1" / "mockups" / "build_admin_explorer.py")], check=True)
subprocess.run([sys.executable, str(ROOT / "q1" / "mockups" / "make_arena.py")], check=True)
shot((ROOT / "q1" / "mockups" / "leaderboard_real.html").as_uri(), out / "mock_lb.png", 1400, 720)
shot((ROOT / "q1" / "mockups" / "admin_real.html").as_uri(), out / "mock_admin.png", 1400, 640)
shot((ROOT / "q1" / "mockups" / "explorer_real.html").as_uri(), out / "mock_explore.png", 1400, 660)
print("screenshots refreshed")
