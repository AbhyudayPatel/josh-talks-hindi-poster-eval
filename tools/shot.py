"""Headless-Edge helpers: screenshot an HTML file, or print HTML to PDF."""
import subprocess, pathlib, sys, tempfile

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def shot(html_path, png_path, w=1400, h=1000, wait_ms=2500):
    html_path, png_path = pathlib.Path(html_path).resolve(), pathlib.Path(png_path).resolve()
    with tempfile.TemporaryDirectory() as prof:
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={prof}",
                        f"--window-size={w},{h}", f"--virtual-time-budget={wait_ms}", f"--screenshot={png_path}",
                        html_path.as_uri()], check=True, capture_output=True, timeout=180)
    return png_path


def pdf(html_path, pdf_path):
    html_path, pdf_path = pathlib.Path(html_path).resolve(), pathlib.Path(pdf_path).resolve()
    with tempfile.TemporaryDirectory() as prof:
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", f"--user-data-dir={prof}", "--no-pdf-header-footer",
                        "--virtual-time-budget=8000", f"--print-to-pdf={pdf_path}", html_path.as_uri()],
                       check=True, capture_output=True, timeout=300)
    return pdf_path


if __name__ == "__main__":
    shot(*sys.argv[1:3])
