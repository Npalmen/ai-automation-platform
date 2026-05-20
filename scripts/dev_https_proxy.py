"""
Local HTTPS reverse proxy for Visma OAuth callback development.

Listens on: https://localhost:44300
Forwards to: http://localhost:8000

This allows Visma's registered redirect_uri (https://localhost:44300/callback)
to reach the local FastAPI app running on http://localhost:8000.

Usage:
    python scripts/dev_https_proxy.py

First run generates a self-signed cert in scripts/.dev-certs/.
Browser will show a security warning — this is expected for local dev.
"""

import http.server
import os
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path

LISTEN_HOST = "localhost"
LISTEN_PORT = 44300
UPSTREAM = "http://localhost:8000"

CERT_DIR = Path(__file__).parent / ".dev-certs"
CERT_FILE = CERT_DIR / "localhost.pem"
KEY_FILE = CERT_DIR / "localhost-key.pem"


def generate_self_signed_cert():
    """Generate a self-signed certificate for localhost using Python's ssl module."""
    CERT_DIR.mkdir(parents=True, exist_ok=True)

    if CERT_FILE.exists() and KEY_FILE.exists():
        print(f"  Certs already exist at {CERT_DIR}")
        return

    print("  Generating self-signed certificate for localhost...")

    try:
        # Try openssl first (better SAN support)
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(KEY_FILE),
                "-out", str(CERT_FILE),
                "-days", "365",
                "-nodes",
                "-subj", "/CN=localhost",
                "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
            ],
            check=True,
            capture_output=True,
        )
        print("  Certificate generated via openssl.")
    except (FileNotFoundError, subprocess.CalledProcessError):
        # Fallback: generate via Python cryptography-free approach
        # Use a minimal self-signed cert via ssl module hack
        _generate_cert_python_fallback()


def _generate_cert_python_fallback():
    """Generate cert using Python subprocess calling itself."""
    script = '''
import ssl, tempfile, subprocess, sys
from pathlib import Path

cert_dir = Path(sys.argv[1])
# Use python -c with ssl to create a basic self-signed cert
import socket, datetime

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    with open(cert_dir / "localhost.pem", "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(cert_dir / "localhost-key.pem", "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    print("OK")
except ImportError:
    print("NEED_OPENSSL")
'''
    result = subprocess.run(
        [sys.executable, "-c", script, str(CERT_DIR)],
        capture_output=True, text=True,
    )
    if "OK" in result.stdout:
        print("  Certificate generated via Python cryptography.")
    else:
        # Last resort: use a pre-baked tiny cert generator
        _generate_cert_stdlib()


def _generate_cert_stdlib():
    """Absolute last resort — invoke openssl via Python's test support."""
    # Generate using make_ssl_certs approach
    import tempfile
    print("  Attempting cert generation via stdlib workaround...")

    # Write a minimal openssl config
    config = CERT_DIR / "openssl.cnf"
    config.write_text(
        "[req]\n"
        "distinguished_name = req_dn\n"
        "x509_extensions = v3_req\n"
        "prompt = no\n"
        "[req_dn]\n"
        "CN = localhost\n"
        "[v3_req]\n"
        "subjectAltName = DNS:localhost,IP:127.0.0.1\n"
    )

    # Try system openssl
    for openssl_cmd in ["openssl", r"C:\Program Files\Git\usr\bin\openssl.exe"]:
        try:
            subprocess.run(
                [
                    openssl_cmd, "req", "-x509", "-newkey", "rsa:2048",
                    "-keyout", str(KEY_FILE),
                    "-out", str(CERT_FILE),
                    "-days", "365", "-nodes",
                    "-config", str(config),
                ],
                check=True, capture_output=True,
            )
            print(f"  Certificate generated via {openssl_cmd}.")
            config.unlink(missing_ok=True)
            return
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue

    config.unlink(missing_ok=True)
    print("  ERROR: Cannot generate SSL certificate.")
    print("  Install openssl or run: pip install cryptography")
    print("  Then re-run this script.")
    sys.exit(1)


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    """Forward all requests to the upstream FastAPI app."""

    def do_GET(self):
        self._proxy()

    def do_POST(self):
        self._proxy()

    def _proxy(self):
        upstream_url = f"{UPSTREAM}{self.path}"
        try:
            # Read request body if present
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else None

            req = urllib.request.Request(upstream_url, data=body, method=self.command)
            # Forward relevant headers
            for header in ("Content-Type", "X-API-Key", "X-Admin-API-Key", "X-Tenant-ID", "Authorization"):
                if header in self.headers:
                    req.add_header(header, self.headers[header])

            with urllib.request.urlopen(req, timeout=30) as resp:
                status = resp.status
                response_body = resp.read()
                content_type = resp.headers.get("Content-Type", "application/json")

            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

        except urllib.error.HTTPError as e:
            body = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", e.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        except Exception as e:
            error_msg = f'{{"detail":"Proxy error: upstream unreachable"}}'.encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error_msg)))
            self.end_headers()
            self.wfile.write(error_msg)

    def log_message(self, format, *args):
        # Clean log without secrets
        print(f"  [{self.command}] {self.path} -> {UPSTREAM}{self.path}")


def main():
    print("=" * 60)
    print("  Visma OAuth Local HTTPS Proxy")
    print("=" * 60)
    print(f"  Listen: https://{LISTEN_HOST}:{LISTEN_PORT}")
    print(f"  Forward: {UPSTREAM}")
    print()

    generate_self_signed_cert()

    if not CERT_FILE.exists() or not KEY_FILE.exists():
        print("  FATAL: No SSL certificates available.")
        sys.exit(1)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(CERT_FILE), str(KEY_FILE))

    server = http.server.HTTPServer((LISTEN_HOST, LISTEN_PORT), ProxyHandler)
    server.socket = context.wrap_socket(server.socket, server_side=True)

    print()
    print(f"  READY: https://localhost:{LISTEN_PORT}")
    print(f"  Visma callback will arrive at: https://localhost:{LISTEN_PORT}/callback")
    print(f"  Forwarding to: {UPSTREAM}/callback")
    print()
    print("  Press Ctrl+C to stop.")
    print("-" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Proxy stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
