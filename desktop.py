"""Run the packaged dashboard and API from one loopback address."""

import os
from pathlib import Path
import socket
import sys
from threading import Thread
import time
from urllib.request import urlopen
import webbrowser

from fastapi.staticfiles import StaticFiles
import uvicorn


def main():
    root = Path(__file__).resolve().parent
    bundle = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else None
    data = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'Didban' / 'data'
    if '--self-test' in sys.argv:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory(prefix='didban-test-') as temporary_data:
            run(bundle, temporary_data, self_test=True)
    else:
        run(bundle, os.environ.get('DIDBAN_DATA_DIR', str(data)), self_test=False)


def run(bundle, data_dir, *, self_test):
    os.environ['DIDBAN_DATA_DIR'] = data_dir
    if bundle:
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(bundle / 'chromium')
    frontend = bundle / 'dashboard' if bundle else Path(__file__).resolve().parent / 'frontend' / 'out'
    if not frontend.is_dir():
        raise SystemExit('Dashboard files missing. Run build-exe.ps1 to build Didban.exe.')

    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        url = f'http://127.0.0.1:{listener.getsockname()[1]}'
        os.environ['DIDBAN_LOCAL_ORIGIN'] = url

        from app import app, index

        app.router.routes.remove(next(route for route in app.router.routes if route.endpoint is index))
        app.mount('/', StaticFiles(directory=frontend, html=True), name='dashboard')
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', log_level='warning',
                                               loop='asyncio', http='h11', ws='none', lifespan='off'))
        print(f'Didban: {url} (Ctrl+C to stop)', flush=True)
        if self_test:
            from playwright.sync_api import sync_playwright

            worker = Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
            worker.start()
            try:
                for _ in range(100):
                    if server.started:
                        break
                    time.sleep(0.1)
                with urlopen(url, timeout=5) as response:
                    assert response.status == 200
                with urlopen(url + '/api/projects', timeout=5) as response:
                    assert response.status == 200
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(channel='chromium', headless=True)
                    page = browser.new_page()
                    page.goto(url)
                    page.get_by_role('heading', name='خلاصهٔ پروژه‌ها').wait_for()
                    browser.close()
                print('PASS: dashboard, API and Chromium')
            finally:
                server.should_exit = True
                worker.join(10)
        else:
            def show_dashboard():
                for _ in range(100):
                    if server.started:
                        webbrowser.open(url)
                        return
                    time.sleep(0.1)

            Thread(target=show_dashboard, daemon=True).start()
            server.run(sockets=[listener])


if __name__ == '__main__':
    main()
