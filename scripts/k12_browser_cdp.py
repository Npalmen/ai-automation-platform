"""
Minimal synchronous Chrome DevTools Protocol (CDP) client.

Uses stdlib only — no Playwright/Selenium. Requires Chromium/Chrome on PATH.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class CdpError(RuntimeError):
    """CDP failure with bounded diagnostic context (no secrets)."""

    def __init__(
        self,
        message: str,
        *,
        method: str | None = None,
        target_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        super().__init__(message)
        self.method = method
        self.target_url = target_url
        self.timeout = timeout

    def detail(self) -> str:
        parts = [type(self).__name__, str(self)]
        if self.method:
            parts.append(f"method={self.method}")
        if self.target_url:
            parts.append(f"target={self.target_url}")
        if self.timeout is not None:
            parts.append(f"timeout={self.timeout}s")
        return " | ".join(parts)


def find_chrome_binary(explicit: str | None = None) -> str:
    if explicit and Path(explicit).is_file():
        return explicit
    for name in (
        "chromium",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
        "chrome",
    ):
        path = shutil.which(name)
        if path:
            return path
    raise CdpError("Chromium/Chrome binary not found on PATH")


def _obtain_page_ws_url(port: int, timeout: float = 20.0) -> str:
    """
    Return a page-target websocket URL.

    /json/version exposes the browser target where Page.* is unavailable.
    Page commands require a devtools/page target from /json/new or /json/list.
    """
    deadline = time.time() + timeout
    last_error = "unknown"
    while time.time() < deadline:
        for url in (
            f"http://127.0.0.1:{port}/json/new?about:blank",
            f"http://127.0.0.1:{port}/json/new",
        ):
            for method in ("PUT", "GET"):
                try:
                    req = urllib.request.Request(url, method=method)
                    with urllib.request.urlopen(req, timeout=1) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                    ws_url = data.get("webSocketDebuggerUrl")
                    if ws_url and "/devtools/page/" in ws_url:
                        return ws_url
                except Exception as exc:
                    last_error = str(exc)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as resp:
                targets = json.loads(resp.read().decode("utf-8"))
            for target in targets:
                if target.get("type") != "page":
                    continue
                ws_url = target.get("webSocketDebuggerUrl")
                if ws_url and "/devtools/page/" in ws_url:
                    return ws_url
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.2)
    raise CdpError(
        f"could not obtain page CDP websocket URL ({last_error})",
        timeout=timeout,
    )
    if explicit and Path(explicit).is_file():
        return explicit
    for name in (
        "chromium",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
        "chrome",
    ):
        path = shutil.which(name)
        if path:
            return path
    raise CdpError("Chromium/Chrome binary not found on PATH")


def _ws_connect(ws_url: str, timeout: float = 10.0) -> socket.socket:
    parsed = urlparse(ws_url)
    if parsed.scheme not in {"ws", "wss"}:
        raise CdpError(f"unsupported websocket scheme: {parsed.scheme}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    sock = socket.create_connection((host, port), timeout=timeout)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    sock.sendall(request.encode("ascii"))
    response = b""
    while b"\r\n\r\n" not in response:
        chunk = sock.recv(4096)
        if not chunk:
            raise CdpError("websocket handshake failed")
        response += chunk
    if b" 101 " not in response.split(b"\r\n", 1)[0]:
        raise CdpError("websocket upgrade rejected")
    return sock


def _ws_send(sock: socket.socket, payload: str) -> None:
    data = payload.encode("utf-8")
    length = len(data)
    header = bytearray()
    header.append(0x81)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack(">H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack(">Q", length))
    mask = os.urandom(4)
    header.extend(mask)
    masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(data))
    sock.sendall(header + masked)


def _ws_recv(sock: socket.socket, timeout: float = 30.0) -> str:
    sock.settimeout(timeout)
    header = sock.recv(2)
    if len(header) < 2:
        raise CdpError("websocket closed")
    b1, b2 = header[0], header[1]
    opcode = b1 & 0x0F
    masked = bool(b2 & 0x80)
    length = b2 & 0x7F
    if length == 126:
        length = struct.unpack(">H", sock.recv(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", sock.recv(8))[0]
    mask = sock.recv(4) if masked else b""
    payload = bytearray()
    while len(payload) < length:
        payload.extend(sock.recv(length - len(payload)))
    if masked:
        payload = bytearray(b ^ mask[i % 4] for i, b in enumerate(payload))
    if opcode == 8:
        raise CdpError("websocket closed by peer")
    if opcode != 1:
        return _ws_recv(sock, timeout=timeout)
    return bytes(payload).decode("utf-8", errors="replace")


@dataclass
class CdpBrowser:
    chrome_path: str
    headless: bool = True
    user_data_dir: Path | None = None
    proc: subprocess.Popen[str] | None = None
    sock: socket.socket | None = None
    msg_id: int = 0
    console_errors: list[dict[str, Any]] = field(default_factory=list)
    _temp_profile: Path | None = None
    debug_port: int | None = None
    ws_url: str | None = None

    def start(self) -> None:
        if self.user_data_dir is None:
            self._temp_profile = Path(tempfile.mkdtemp(prefix="k12-browser-"))
            self.user_data_dir = self._temp_profile
        port_sock = socket.socket()
        port_sock.bind(("127.0.0.1", 0))
        port = port_sock.getsockname()[1]
        port_sock.close()
        self.debug_port = port

        args = [
            self.chrome_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={self.user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-extensions",
            "--disable-dev-shm-usage",
            # Required when the matrix runs as root (sudo/cron on pilot).
            "--no-sandbox",
        ]
        if self.headless:
            args.extend(["--headless=new", "--disable-gpu"])
        self.proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        try:
            ws_url = _obtain_page_ws_url(port, timeout=20.0)
        except CdpError:
            self.close()
            raise
        self.ws_url = ws_url
        self.sock = _ws_connect(ws_url)
        self.call("Page.enable", timeout=15.0)
        self.call("Runtime.enable", timeout=15.0)
        self.call("Log.enable", timeout=15.0)
        self.call("Network.enable", timeout=15.0)
        self.call("DOM.enable", timeout=15.0)
        self._drain_events(timeout=0.5)

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None
        if self._temp_profile and self._temp_profile.exists():
            shutil.rmtree(self._temp_profile, ignore_errors=True)
            self._temp_profile = None

    def _drain_events(self, timeout: float = 0.0) -> None:
        if not self.sock:
            return
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self.sock.settimeout(max(0.05, deadline - time.time()))
                message = json.loads(_ws_recv(self.sock, timeout=0.5))
            except (socket.timeout, TimeoutError, json.JSONDecodeError):
                break
            if "method" not in message:
                continue
            method = message["method"]
            params = message.get("params") or {}
            if method == "Runtime.consoleAPICalled":
                level = params.get("type", "log")
                if level in {"error", "warning"}:
                    self.console_errors.append(
                        {
                            "level": level,
                            "text": _console_text(params.get("args") or []),
                        }
                    )
            elif method == "Log.entryAdded":
                entry = params.get("entry") or {}
                if entry.get("level") in {"error", "warning"}:
                    self.console_errors.append(
                        {
                            "level": entry.get("level"),
                            "text": entry.get("text", ""),
                        }
                    )

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 30.0) -> dict[str, Any]:
        if not self.sock:
            raise CdpError("browser not started", method=method, target_url=self.ws_url, timeout=timeout)
        self.msg_id += 1
        msg_id = self.msg_id
        payload = {"id": msg_id, "method": method, "params": params or {}}
        _ws_send(self.sock, json.dumps(payload))
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.sock.settimeout(max(0.1, deadline - time.time()))
            raw = _ws_recv(self.sock, timeout=max(0.1, deadline - time.time()))
            message = json.loads(raw)
            if message.get("id") != msg_id:
                if "method" in message:
                    params_in = message.get("params") or {}
                    if message["method"] == "Runtime.consoleAPICalled":
                        level = params_in.get("type", "log")
                        if level in {"error", "warning"}:
                            self.console_errors.append(
                                {
                                    "level": level,
                                    "text": _console_text(params_in.get("args") or []),
                                }
                            )
                continue
            if "error" in message:
                err = message["error"]
                msg = err.get("message") if isinstance(err, dict) else str(err)
                raise CdpError(
                    msg or str(err),
                    method=method,
                    target_url=self.ws_url,
                    timeout=timeout,
                )
            return message.get("result") or {}
        raise CdpError(
            f"timeout waiting for {method}",
            method=method,
            target_url=self.ws_url,
            timeout=timeout,
        )

    def navigate(self, url: str, timeout: float = 30.0) -> None:
        self.call("Page.navigate", {"url": url})
        deadline = time.time() + timeout
        while time.time() < deadline:
            state = self.evaluate("document.readyState")
            if state == "complete":
                time.sleep(0.3)
                self._drain_events(timeout=0.2)
                return
            time.sleep(0.2)
        raise CdpError(
            f"navigation timeout for {url}",
            method="Page.navigate",
            target_url=url,
            timeout=timeout,
        )

    def evaluate(self, expression: str, timeout: float = 15.0) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
            timeout=timeout,
        )
        if result.get("exceptionDetails"):
            raise CdpError(
                "javascript exception",
                method="Runtime.evaluate",
                target_url=self.ws_url,
                timeout=timeout,
            )
        return (result.get("result") or {}).get("value")

    def set_viewport(self, width: int, height: int) -> None:
        self.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,
                "mobile": width < 768,
            },
        )

    def set_zoom(self, percent: int) -> None:
        self.call("Emulation.setPageScaleFactor", {"pageScaleFactor": percent / 100.0})

    def capture_screenshot(self, path: Path) -> None:
        result = self.call("Page.captureScreenshot", {"format": "png"})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(result["data"]))

    def current_url(self) -> str:
        return str(self.evaluate("window.location.href") or "")

    def overflow_check(self) -> dict[str, Any]:
        return self.evaluate(
            """(() => {
  const doc = document.documentElement;
  const main = document.querySelector('main');
  const result = {
    document_overflow: doc.scrollWidth > doc.clientWidth,
    document_scroll_width: doc.scrollWidth,
    document_client_width: doc.clientWidth,
  };
  if (main) {
    result.main_overflow = main.scrollWidth > main.clientWidth;
    result.main_scroll_width = main.scrollWidth;
    result.main_client_width = main.clientWidth;
  }
  return result;
})()"""
        )

    def storage_secrets_check(self, secrets: set[str]) -> dict[str, Any]:
        raw = self.evaluate(
            """(() => {
  const keys = [];
  for (let i = 0; i < localStorage.length; i++) keys.push(localStorage.key(i));
  const sessionKeys = [];
  for (let i = 0; i < sessionStorage.length; i++) sessionKeys.push(sessionStorage.key(i));
  return {
    local_storage_keys: keys,
    session_storage_keys: sessionKeys,
    local_storage_values_joined: keys.map(k => localStorage.getItem(k) || '').join(' '),
    session_storage_values_joined: sessionKeys.map(k => sessionStorage.getItem(k) || '').join(' '),
    href: window.location.href,
  };
})()"""
        )
        exposed = False
        haystack = json.dumps(raw, ensure_ascii=False)
        for secret in secrets:
            if secret and secret in haystack:
                exposed = True
        admin_key = any("admin" in (k or "").lower() and "key" in (k or "").lower() for k in raw.get("local_storage_keys", []))
        return {
            "credentials_in_storage": exposed,
            "admin_key_in_local_storage": admin_key,
            "local_storage_key_count": len(raw.get("local_storage_keys", [])),
            "session_storage_key_count": len(raw.get("session_storage_keys", [])),
            "credentials_in_url": any(secret in (raw.get("href") or "") for secret in secrets if secret),
        }

    def accessibility_probe(self) -> dict[str, Any]:
        return self.evaluate(
            """(() => {
  const skip = document.querySelector('a[href="#main-content"]');
  const main = document.getElementById('main-content');
  const skipDisplay = skip ? getComputedStyle(skip).display : null;
  const dialog = document.querySelector('[role="dialog"][aria-modal="true"]');
  const labels = Array.from(document.querySelectorAll('label[for]')).length;
  const focusable = document.querySelector('[class*="focus-visible"]') !== null;
  let skip_focus_works = false;
  if (skip && main) {
    skip.focus();
    skip.click();
    skip_focus_works = document.activeElement === main;
  }
  const doc = document.documentElement;
  return {
    skip_link_present: !!skip,
    main_content_present: !!main,
    skip_link_hidden_until_focus: skip ? (skipDisplay === 'none' || skip.className.includes('sr-only')) : false,
    skip_focus_works,
    document_overflow: doc.scrollWidth > doc.clientWidth,
    aria_modal_dialog_present: !!dialog,
    label_count: labels,
    focus_visible_class_present: focusable,
  };
})()"""
        )


def _console_text(args: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for arg in args:
        val = arg.get("value")
        if val is not None:
            parts.append(str(val))
        elif arg.get("type") == "string" and arg.get("value") is None:
            desc = arg.get("description")
            if desc:
                parts.append(desc)
    return " ".join(parts)[:500]


def redact_console_errors(errors: list[dict[str, Any]], secrets: set[str]) -> list[dict[str, Any]]:
    cleaned = []
    for item in errors:
        text = item.get("text", "")
        for secret in secrets:
            if secret:
                text = text.replace(secret, "[REDACTED]")
        cleaned.append({"level": item.get("level"), "text": text[:300]})
    return cleaned
