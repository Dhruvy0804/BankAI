"""Optional real-browser QA against a disposable local database; no demo data reset."""

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from uuid import uuid4

from alembic import command
from alembic.config import Config
from app.core.config import ROOT, Settings
from app.seed.demo_data import DEMO_PASSWORD, require_local_demo, seed_demo
from playwright.sync_api import Error as BrowserError
from playwright.sync_api import expect, sync_playwright
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def stop(process):
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.terminate()
    process.wait(timeout=10)


def main():
    settings = Settings()
    require_local_demo(settings)
    name = f"bankai_ui_test_{uuid4().hex}"
    url = (
        make_url(settings.database_url)
        .set(database=name)
        .render_as_string(hide_password=False)
    )
    admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    server = frontend = None
    page = None
    created = False
    output = ROOT / ".artifacts"
    output.mkdir(exist_ok=True)
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        created = True
        engine = create_engine(url)
        try:
            with engine.begin() as connection:
                config = Config(str(ROOT / "backend/alembic.ini"))
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
            with Session(engine) as session, session.begin():
                seed_demo(session)
        finally:
            engine.dispose()
        api_port, ui_port = port(), port()
        environment = os.environ | {
            "DATABASE_URL": url,
            "APP_ENV": "development",
            "APP_SECRET_KEY": secrets.token_urlsafe(48),
            "API_PROXY_TARGET": f"http://127.0.0.1:{api_port}",
        }
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
            ],
            cwd=ROOT / "backend",
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        frontend = subprocess.Popen(
            [
                shutil.which("node"),
                str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                "--host",
                "127.0.0.1",
                "--port",
                str(ui_port),
                "--strictPort",
            ],
            cwd=ROOT / "frontend",
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            for _ in range(60):
                if server.poll() is not None or frontend.poll() is not None:
                    raise RuntimeError("A QA server exited before startup")
                try:
                    response = context.request.get(
                        f"http://127.0.0.1:{ui_port}/api/ready", timeout=1000
                    )
                    if response.ok:
                        break
                except BrowserError:
                    time.sleep(0.25)
                    continue
                time.sleep(0.25)
            else:
                raise RuntimeError("QA servers did not become ready")
            page.goto(f"http://127.0.0.1:{ui_port}")
            page.screenshot(path=str(output / "login-desktop.png"), full_page=True)
            page.get_by_label("Email address").fill("demo.asha@bankai.example")
            page.get_by_label("Password", exact=True).fill(DEMO_PASSWORD)
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(
                page.get_by_role("heading", name="Welcome, Demo Asha", exact=True)
            ).to_be_visible()
            expect(page.get_by_text("₹11,825.25", exact=True)).to_be_visible()
            page.screenshot(path=str(output / "dashboard-desktop.png"), full_page=True)
            page.reload()
            expect(
                page.get_by_role("heading", name="Welcome, Demo Asha", exact=True)
            ).to_be_visible()
            page.get_by_role("link", name="Accounts", exact=True).click()
            page.get_by_label("Account details").select_option(
                label="DEMO-ACCT-0001 · savings"
            )
            expect(page.get_by_role("button", name="Refresh balance")).to_be_visible()
            page.get_by_role("link", name="Transactions", exact=True).click()
            expect(page.get_by_role("table")).to_be_visible()
            page.get_by_label("Type", exact=True).select_option("debit")
            page.get_by_role("button", name="Apply filters").click()
            expect(
                page.get_by_text("Demo grocery purchase", exact=True).first
            ).to_be_visible()
            page.get_by_role("link", name="Cards", exact=True).click()
            page.get_by_role("button", name="Block demo card").click()
            expect(page.get_by_role("dialog")).to_be_visible()
            expect(page.get_by_role("button", name="Cancel")).to_be_focused()
            page.keyboard.press("Escape")
            expect(page.get_by_role("dialog")).not_to_be_visible()
            expect(page.get_by_role("button", name="Block demo card")).to_be_focused()
            page.get_by_role("button", name="Block demo card").click()
            page.screenshot(path=str(output / "card-confirmation.png"), full_page=True)
            page.get_by_role("button", name="Confirm action").click()
            expect(
                page.get_by_text("DEMO-XXXX-0001 was blocked in BankSim.")
            ).to_be_visible()
            page.get_by_role("link", name="Loans", exact=True).click()
            page.get_by_label("Loan amount (INR)").fill("12000")
            page.get_by_label("Annual interest (%)").fill("12")
            page.get_by_label("Tenure (months)").fill("12")
            page.get_by_role("button", name="Calculate EMI").click()
            expect(page.get_by_text("₹1,066.19", exact=True)).to_be_visible()
            page.get_by_label("Demo monthly income (INR)").fill("50000")
            page.get_by_role("button", name="Check eligibility").click()
            expect(
                page.get_by_text("Eligible under demo rules", exact=True)
            ).to_be_visible()
            page.get_by_role("button", name="Request application").click()
            expect(page.get_by_role("dialog")).to_contain_text("₹12,000.00")
            page.get_by_role("button", name="Confirm action").click()
            expect(
                page.get_by_text(
                    "Your simulated loan application was submitted. This is not credit approval."
                )
            ).to_be_visible()
            page.get_by_role("link", name="Support", exact=True).click()
            page.get_by_label("Subject", exact=True).fill("Demo browser QA inquiry")
            page.get_by_label("Description", exact=True).fill(
                "Fictional issue created only in an isolated QA database."
            )
            page.get_by_role("button", name="Create demo ticket").click()
            expect(
                page.get_by_text("Your demo support ticket was created.")
            ).to_be_visible()
            expect(
                page.get_by_role("heading", name="Demo browser QA inquiry")
            ).to_be_visible()
            page.set_viewport_size({"width": 390, "height": 844})
            for title in (
                "Dashboard",
                "Accounts",
                "Transactions",
                "Cards",
                "Loans",
                "Support",
                "About",
            ):
                page.get_by_role("link", name=title, exact=True).click()
                expect(page.get_by_role("heading", level=1)).to_be_visible()
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                ), title
                if title == "Dashboard":
                    expect(page.get_by_text("₹11,825.25", exact=True)).to_be_visible()
                    page.screenshot(
                        path=str(output / "dashboard-mobile.png"), full_page=True
                    )
            page.get_by_role("button", name="Sign out", exact=True).click()
            expect(page.get_by_label("Email address")).to_be_visible()
            page.get_by_label("Email address").fill("demo.ravi@bankai.example")
            page.get_by_label("Password", exact=True).fill(DEMO_PASSWORD)
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(
                page.get_by_role("heading", name="Welcome, Demo Ravi", exact=True)
            ).to_be_visible()
            expect(page.get_by_text("DEMO-ACCT-0003", exact=True).first).to_be_visible()
            expect(page.get_by_text("DEMO-ACCT-0001", exact=True)).not_to_be_visible()
            page.route(
                "**/api/v1/auth/me",
                lambda route: route.fulfill(
                    status=401,
                    content_type="application/json",
                    body=json.dumps({"error": {"message": "Expired token"}}),
                ),
            )
            page.reload()
            expect(
                page.get_by_text("Your session ended. Sign in again.")
            ).to_be_visible()
            assert not errors, errors
            browser.close()
        print(
            "Edge desktop/mobile smoke passed: login, refresh, all pages, card/loan confirmation, support, customer switching and expired session; no browser errors."
        )
    except Exception:
        if page is not None and not page.is_closed():
            try:
                page.screenshot(
                    path=str(output / "browser-failure.png"), full_page=True
                )
                (output / "browser-failure.txt").write_text(
                    page.locator("body").inner_text(), encoding="utf-8"
                )
            except (BrowserError, OSError):
                print(
                    "Browser failure capture was unavailable; see the original assertion."
                )
        raise
    finally:
        stop(frontend)
        stop(server)
        if created:
            with admin.connect() as connection:
                # The generated database name is never taken from a user or environment variable.
                connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


if __name__ == "__main__":
    main()
