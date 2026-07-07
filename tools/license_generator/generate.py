"""
Generador de licencias LBAMonitor v4.4 — Programa aparte.

Este programa debe ejecutarse EN LA MÁQUINA DEL LICENSOR (no en el cliente).
Genera licencias firmadas para los clientes basándose en su HWID.

USO (CLI):
    python -m tools.license_generator.generate --machine-id <hwid> --tier pro --days 365

USO (GUI):
    python -m tools.license_generator.gui

SEGURIDAD:
- El secret o private key NUNCA se incluye en el binario del cliente
- El cliente solo tiene la PUBLIC key (RSA) o nada (HMAC con secret compartido)
- RSA-2048 es recomendado (no requiere compartir secret)
- HMAC es más simple pero requiere que el licensor y el cliente compartan el secret

ANTI-CRACKING:
- La licencia incluye timestamp de emisión (no se puede reutilizar)
- La licencia incluye HWID del cliente (no se puede transferir)
- La licencia incluye fecha de expiración
- La firma HMAC/RSA evita modificación de los campos
- El cliente verifica la licencia en cada arranque
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Asegurar que podemos importar lbamonitor
_BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from lbamonitor.core.services.license_engine import generate_license


def _get_secret() -> str:
    """Obtiene el secret HMAC desde env var."""
    secret = os.environ.get("LBAMONITOR_LICENSE__SIGNING_SECRET", "")
    if not secret:
        raise RuntimeError(
            "LBAMONITOR_LICENSE__SIGNING_SECRET no configurado.\n"
            "Este debe ser el MISMO secret que usa el backend del cliente para verificar.\n"
            "Genera uno con: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return secret


def _get_private_key() -> str:
    """Obtiene la private key RSA desde env var o archivo."""
    # 1. Env var directa
    key = os.environ.get("LBAMONITOR_LICENSE__PRIVATE_KEY_PEM", "")
    if key:
        return key

    # 2. Archivo .pem
    key_file = os.environ.get("LBAMONITOR_LICENSE__PRIVATE_KEY_FILE", "")
    if key_file and Path(key_file).is_file():
        return Path(key_file).read_text()

    return ""


def _generate_keypair(output_dir: Path) -> tuple[Path, Path]:
    """Genera un par de claves RSA-2048 nuevo."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError:
        raise RuntimeError(
            "cryptography no instalado. Instalar con: pip install cryptography"
        )

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    output_dir.mkdir(parents=True, exist_ok=True)
    priv_path = output_dir / "private_key.pem"
    pub_path = output_dir / "public_key.pem"

    priv_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    pub_path.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    # Permisos restrictivos en la private key
    priv_path.chmod(0o600)

    return priv_path, pub_path


def generate_license_for_machine(
    machine_id: str,
    tier: str = "pro",
    expires: str | None = None,
    use_rsa: bool = False,
) -> str:
    """
    Genera una licencia para el machine_id dado.

    Args:
        machine_id: HWID de la máquina cliente (string hex de 64 chars)
        tier: "trial" | "pro" | "enterprise"
        expires: fecha ISO (ej. "2026-12-31") o None para sin expiración
        use_rsa: True para usar RSA-2048 (más seguro), False para HMAC

    Returns:
        String de licencia firmada
    """
    if use_rsa:
        private_key = _get_private_key()
        if not private_key:
            raise RuntimeError(
                "RSA seleccionado pero no hay private key.\n"
                "Genera un par con: python -m tools.license_generator.generate --gen-keypair\n"
                "O setea LBAMONITOR_LICENSE__PRIVATE_KEY_PEM o LBAMONITOR_LICENSE__PRIVATE_KEY_FILE"
            )
        return generate_license(
            machine_id=machine_id,
            expires=expires,
            tier=tier,
            private_key_pem=private_key,
        )
    else:
        secret = _get_secret()
        return generate_license(
            machine_id=machine_id,
            expires=expires,
            tier=tier,
            secret=secret,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generador de licencias LBAMonitor v4.4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EJEMPLOS:

  # Generar par de claves RSA (primera vez)
  python -m tools.license_generator.generate --gen-keypair

  # Generar licencia HMAC (simple, requiere secret compartido)
  LBAMONITOR_LICENSE__SIGNING_SECRET=<secret> \\
  python -m tools.license_generator.generate \\
      --machine-id abc123... --tier pro --days 365

  # Generar licencia RSA (recomendado, más seguro)
  LBAMONITOR_LICENSE__PRIVATE_KEY_FILE=private_key.pem \\
  python -m tools.license_generator.generate \\
      --machine-id abc123... --tier pro --expires 2026-12-31 --rsa

  # Generar licencia trial de 10 días
  python -m tools.license_generator.generate \\
      --machine-id abc123... --tier trial --days 10
""",
    )
    parser.add_argument("--machine-id", help="HWID de la máquina cliente (64 chars hex)")
    parser.add_argument("--tier", default="pro", choices=["trial", "pro", "enterprise"])
    parser.add_argument(
        "--expires",
        help="Fecha de expiración ISO (ej. 2026-12-31). Default: +1 año",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Vigencia en días desde hoy (default 365). Se ignora si --expires.",
    )
    parser.add_argument(
        "--rsa",
        action="store_true",
        help="Usar RSA-2048 en lugar de HMAC (más seguro, recomendado)",
    )
    parser.add_argument(
        "--gen-keypair",
        action="store_true",
        help="Generar par de claves RSA-2048 nuevo (primera vez)",
    )
    parser.add_argument(
        "--keypair-dir",
        type=Path,
        default=Path("./keys"),
        help="Directorio donde guardar las claves RSA (default: ./keys)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Archivo donde guardar la licencia (default: stdout)",
    )

    args = parser.parse_args()

    # Modo especial: generar keypair
    if args.gen_keypair:
        print("Generando par de claves RSA-2048...")
        priv, pub = _generate_keypair(args.keypair_dir)
        print(f"✓ Private key: {priv}")
        print(f"✓ Public key:  {pub}")
        print()
        print("INSTRUCCIONES:")
        print(f"1. GUARDA {priv.name} EN LUGAR SEGURO (nunca la compartas)")
        print(f"2. Comparte {pub.name} con el cliente (se configura en su backend)")
        print(f"3. El cliente setea LBAMONITOR_LICENSE__PUBLIC_KEY_PEM con el contenido de {pub.name}")
        print(f"4. Tú (licensor) seteas LBAMONITOR_LICENSE__PRIVATE_KEY_FILE={priv}")
        print(f"5. Genera licencias con --rsa")
        return 0

    # Validar args
    if not args.machine_id:
        parser.error("--machine-id es requerido (a menos que uses --gen-keypair)")

    if args.expires:
        expires = args.expires
    else:
        expires = (datetime.now(timezone.utc) + timedelta(days=args.days)).date().isoformat()

    try:
        license_str = generate_license_for_machine(
            machine_id=args.machine_id,
            tier=args.tier,
            expires=expires,
            use_rsa=args.rsa,
        )

        print("=" * 70)
        print("LICENCIA GENERADA — LBAMonitor v4.4")
        print("=" * 70)
        print(f"Machine ID: {args.machine_id}")
        print(f"Tier:       {args.tier}")
        print(f"Expira:     {expires}")
        print(f"Algoritmo:  {'RSA-2048' if args.rsa else 'HMAC-SHA256'}")
        print("-" * 70)
        print("Licencia (copia y pega en el cliente):")
        print(license_str)
        print("=" * 70)

        if args.output:
            args.output.write_text(license_str)
            print(f"\nLicencia guardada en: {args.output}")

        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
