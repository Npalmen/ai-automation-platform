#!/usr/bin/env python3
"""Focused pilot browser check: super_admin sees Ny kund on /ops/customers."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path("/opt/krowolf")
sys.path.insert(0, str(ROOT))

from scripts.k12_browser_cdp import CdpBrowser, find_chrome_binary  # noqa: E402
from scripts.k12_browser_common import load_browser_env, resolve_env_path  # noqa: E402

BASE = "https://api.krowolf.se"


def login(browser: CdpBrowser, username: str, password: str) -> None:
    browser.navigate(f"{BASE}/ops/login")
    result = browser.evaluate(
        f"""(() => {{
  function setNativeValue(element, value) {{
    const proto = element instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(proto, "value");
    descriptor.set.call(element, value);
    element.dispatchEvent(new Event("input", {{ bubbles: true }}));
    element.dispatchEvent(new Event("change", {{ bubbles: true }}));
  }}
  const u = document.querySelector('input[name="username"]');
  const p = document.querySelector('input[name="password"]');
  const form = document.querySelector("form");
  if (!u || !p || !form) return {{ ok: false }};
  setNativeValue(u, {json.dumps(username)});
  setNativeValue(p, {json.dumps(password)});
  if (typeof form.requestSubmit === "function") form.requestSubmit();
  else form.querySelector('button[type="submit"]')?.click();
  return {{ ok: true }};
}})()"""
    )
    if not result or not result.get("ok"):
        raise RuntimeError("login_form_missing")
    deadline = time.time() + 30
    while time.time() < deadline:
        me = browser.evaluate(
            """(async () => {
  const r = await fetch('/auth/admin/me', { credentials: 'include' });
  const d = await r.json().catch(() => ({}));
  return { status: r.status, role: d?.operator?.role, id: d?.operator?.id };
})()"""
        )
        if me and me.get("status") == 200:
            return
        time.sleep(0.3)
    raise RuntimeError("login_timeout")


def main() -> int:
    env = load_browser_env(resolve_env_path())
    username = env.get("K12_BROWSER_USERNAME") or env.get("ADMIN_USERNAME") or "admin"
    password = env.get("K12_BROWSER_PASSWORD") or env.get("ADMIN_PASSWORD") or ""
    chrome = find_chrome_binary()
    if not chrome:
        print(json.dumps({"error": "no_chrome"}))
        return 1

    browser = CdpBrowser(chrome_path=chrome, headless=True)
    browser.start()
    try:
        login(browser, username, password)
        me = browser.evaluate(
            """(async () => {
  const r = await fetch('/auth/admin/me', { credentials: 'include' });
  const d = await r.json();
  return { status: r.status, authenticated: d.authenticated, role: d.operator?.role, id: d.operator?.id, display_name: d.operator?.display_name, environment: d.environment };
})()"""
        )
        browser.navigate(f"{BASE}/ops/customers")
        time.sleep(1.5)
        dom = browser.evaluate(
            """(() => {
  const buttons = Array.from(document.querySelectorAll('button')).map(b => (b.textContent || '').trim()).filter(Boolean);
  const scripts = Array.from(document.querySelectorAll('script[src]')).map(s => s.getAttribute('src'));
  return {
    url: location.href,
    title: document.title,
    h1: document.querySelector('h1')?.textContent?.trim() || null,
    buttons,
    hasNyKund: buttons.includes('Ny kund') || (document.body?.innerText || '').includes('Ny kund'),
    scriptSrc: scripts,
  };
})()"""
        )
        if dom and dom.get("hasNyKund"):
            browser.evaluate("""(() => {
  const btn = Array.from(document.querySelectorAll('button')).find(b => (b.textContent || '').trim() === 'Ny kund');
  if (btn) btn.click();
})()""")
            time.sleep(1.0)
            after_click = browser.evaluate(
                "({ url: location.href, h1: document.querySelector('h1')?.textContent?.trim() || null })"
            )
        else:
            after_click = None

        report = {
            "me": me,
            "dom": dom,
            "after_click": after_click,
            "console_errors": browser.console_errors[:5],
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        ok = (
            (me or {}).get("role") == "super_admin"
            and bool((dom or {}).get("hasNyKund"))
            and (after_click or {}).get("url", "").endswith("/ops/customers/new")
        )
        return 0 if ok else 1
    finally:
        browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
