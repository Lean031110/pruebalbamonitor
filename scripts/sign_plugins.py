"""
Firma plugins con HMAC-SHA256.

Genera archivos .py.sig junto a cada .py en backend/plugins/.

USO:
    LBAMONITOR_PLUGINS_SIGNING_KEY=<secret> python scripts/sign_plugins.py
"""
import hashlib
import hmac
import os
import sys
from pathlib import Path

def sign_all_plugins():
    key = os.environ.get("LBAMONITOR_PLUGINS_SIGNING_KEY", "")
    if not key:
        print("ERROR: LBAMONITOR_PLUGINS_SIGNING_KEY no configurado.")
        print("Genera uno con: python -c \"import secrets; print(secrets.token_hex(32))\"")
        return 1

    plugins_dir = Path(__file__).resolve().parent.parent / "backend" / "plugins"
    if not plugins_dir.is_dir():
        print(f"ERROR: {plugins_dir} no existe")
        return 1

    print(f"Firmando plugins en {plugins_dir}...")
    key_bytes = key.encode("utf-8")
    count = 0
    for py in sorted(plugins_dir.glob("*.py")):
        if py.name.startswith("_"):
            continue
        sig = hmac.new(key_bytes, py.read_bytes(), hashlib.sha256).hexdigest()
        sig_file = py.with_suffix(".py.sig")
        sig_file.write_text(sig)
        print(f"  ✓ {py.name} → {sig_file.name} ({sig[:16]}...)")
        count += 1

    print(f"\n{count} plugin(s) firmado(s).")
    print("Los archivos .sig deben distribuirse junto con los .py.")
    return 0

if __name__ == "__main__":
    sys.exit(sign_all_plugins())
