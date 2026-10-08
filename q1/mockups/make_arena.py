"""Turn the three real-data screens into one clickable demo ("Bharat Poster Arena").

Replaces each screen's decorative tab row with working links between:
Leaderboard -> leaderboard_real.html, Explore failures -> explorer_real.html, Admin -> admin_real.html,
Rate posters -> ../rating_app/rate.html. Open q1/mockups/arena.html (or any of the pages) in a browser.
"""
import pathlib, re

HERE = pathlib.Path(__file__).parent
PAGES = [("Leaderboard", "leaderboard_real.html"), ("Explore failures", "explorer_real.html"),
         ("Admin", "admin_real.html"), ("Rate posters ↗", "../rating_app/rate.html")]
STYLE = ("<style>.tabs a{padding:6px 12px;color:var(--text-secondary);text-decoration:none;font-size:13px}"
         ".tabs a.a{background:#111;color:#fff;font-weight:600}.tabs a:hover:not(.a){background:#f2f2f2}</style>")

for _, f in PAGES[:3]:
    p = HERE / f
    s = p.read_text(encoding="utf-8")
    nav = "".join(f'<a href="{href}" class="{"a" if href == f else ""}">{label}</a>' for label, href in PAGES)
    s = re.sub(r'<div class="tabs">.*?</div></div>', f'<div class="tabs">{nav}</div>', s, count=1, flags=re.S)
    s = re.sub(r'Bharat <span>Poster</span> Arena · <span[^>]*>Admin</span>', 'Bharat <span>Poster</span> Arena', s)
    if STYLE not in s:
        s = s.replace("</head>", STYLE + "</head>", 1)
    p.write_text(s, encoding="utf-8")

(HERE / "arena.html").write_text('<!doctype html><meta http-equiv="refresh" content="0; url=leaderboard_real.html">', encoding="utf-8")
print("arena ready: open q1/mockups/arena.html")
