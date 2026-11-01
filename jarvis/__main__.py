"""`python -m jarvis` (or jarvis.exe): start the local server and open the browser."""

import argparse
import threading
import webbrowser

import httpx
import uvicorn


def main():
    ap = argparse.ArgumentParser(prog="jarvis")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    url = f"http://{a.host}:{a.port}"
    try:  # a second launch just opens the copy that is already running
        if httpx.get(url + "/api/health", timeout=1).status_code == 200:
            print(f"Mozhi is already running at {url}")
            if not a.no_browser:
                webbrowser.open(url)
            return
    except httpx.HTTPError:
        pass
    if not a.no_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    from jarvis import llm
    from jarvis.server import app

    s = llm.settings()
    print(f"Mozhi is running at {url}  (close this window or press Ctrl+C to quit)")
    print(f"Language model: {s['model'] if s['endpoint'] else 'none connected'}; OmniRoute is started for you if it is local and not running, and stopped on exit only if Mozhi started it.")
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
