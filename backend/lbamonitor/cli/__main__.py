"""CLI de administración de LBAMonitor (lbamonitor-cli)."""
from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from lbamonitor import __version__

console = Console()


@click.group(help="LBAMonitor CLI — herramienta de administración.")
@click.version_option(__version__, "-V", "--version", prog_name="lbamonitor-cli")
def cli() -> None:
    """Grupo principal de comandos."""


@cli.command()
def version() -> None:
    """Muestra la versión."""
    console.print(f"LBAMonitor v{__version__}")


@cli.command()
def config() -> None:
    """Muestra la configuración cargada."""
    from lbamonitor.core.config import get_settings
    s = get_settings()
    table = Table(title="Configuración LBAMonitor")
    table.add_column("Sección", style="cyan")
    table.add_column("Clave", style="magenta")
    table.add_column("Valor", style="green")
    for section_name in ("server", "database", "monitoring", "backup", "logging", "license", "appearance", "business", "pricing", "paths"):
        section = getattr(s, section_name)
        for k, v in section.model_dump().items():
            table.add_row(section_name, k, str(v))
    console.print(table)


@cli.command()
@click.option("--reset", is_flag=True, help="Eliminar BD existente antes de crear.")
@click.option(
    "--with-admin", is_flag=True, default=True,
    help="Crear usuario admin por defecto (admin/admin123). Cámbialo tras el primer login.",
)
def init_db(reset: bool, with_admin: bool) -> None:
    """Crea el esquema de la base de datos (modo desarrollo) y usuario admin inicial."""
    import asyncio
    from lbamonitor.core.db import (
        create_all_tables, drop_all_tables, init_engine, dispose_engine, get_session_factory,
    )

    async def _run():
        await init_engine()
        if reset:
            console.print("[yellow]Eliminando tablas existentes...[/]")
            from lbamonitor.core.db import drop_all_tables
            await drop_all_tables()
        console.print("[cyan]Creando tablas...[/]")
        await create_all_tables()

        if with_admin:
            console.print("[cyan]Creando usuario admin por defecto...[/]")
            from lbamonitor.core.models import User
            from lbamonitor.utils.helpers import hash_password, utcnow
            from sqlalchemy import select

            factory = get_session_factory()
            async with factory() as session:
                # Verificar si ya existe admin
                existing = await session.execute(select(User).where(User.username == "admin"))
                if existing.scalar_one_or_none():
                    console.print("[yellow]Usuario 'admin' ya existe, omitiendo creación.[/]")
                else:
                    admin = User(
                        username="admin",
                        password_hash=hash_password("admin123"),
                        role="admin",
                        active=True,
                        full_name="Administrador",
                        created_at=utcnow(),
                    )
                    session.add(admin)
                    await session.commit()
                    console.print("[green]Usuario admin creado: admin / admin123[/]")
                    console.print("[yellow]¡CAMBIA LA CONTRASEÑA TRAS EL PRIMER LOGIN![/]")

        # Inicializar niveles de membresía por defecto
        console.print("[cyan]Inicializando niveles de membresía...[/]")
        from lbamonitor.core.repositories.business_repository import MembershipLevelRepository
        factory = get_session_factory()
        async with factory() as session:
            repo = MembershipLevelRepository(session)
            await repo.initialize_defaults()
            await session.commit()
        console.print("[green]Niveles bronce/plata/oro/platino/diamante creados ✓[/]")

        await dispose_engine()
        console.print("[green bold]Inicialización completa ✓[/]")

    asyncio.run(_run())


@cli.command(name="create-admin")
@click.option("--username", required=True, help="Nombre de usuario.")
@click.option("--password", required=True, help="Contraseña (se hashea).")
@click.option("--role", default="admin", type=click.Choice(["admin", "operator", "viewer"]))
@click.option("--full-name", default="", help="Nombre completo.")
def create_admin(username: str, password: str, role: str, full_name: str) -> None:
    """Crea o actualiza un usuario del sistema."""
    import asyncio
    from lbamonitor.core.db import init_engine, dispose_engine, get_session_factory
    from lbamonitor.core.models import User
    from lbamonitor.utils.helpers import hash_password, utcnow
    from sqlalchemy import select

    async def _run():
        await init_engine()
        factory = get_session_factory()
        async with factory() as session:
            existing = await session.execute(select(User).where(User.username == username))
            user = existing.scalar_one_or_none()
            if user:
                user.password_hash = hash_password(password)
                user.role = role
                if full_name:
                    user.full_name = full_name
                console.print(f"[green]Usuario '{username}' actualizado.[/]")
            else:
                user = User(
                    username=username,
                    password_hash=hash_password(password),
                    role=role,
                    active=True,
                    full_name=full_name or username,
                    created_at=utcnow(),
                )
                session.add(user)
                console.print(f"[green]Usuario '{username}' creado con rol '{role}'.[/]")
            await session.commit()
        await dispose_engine()

    asyncio.run(_run())


@cli.command()
def machine_id() -> None:
    """Calcula y muestra el Machine ID (HWID) de esta máquina."""
    from lbamonitor.core.services.license_engine import compute_machine_id
    hwid = compute_machine_id()
    console.print(f"[cyan]Machine ID:[/] [bold]{hwid}[/]")


@cli.command()
@click.option("--machine-id", required=True, help="Machine ID destino.")
@click.option("--expires", required=False, help="Fecha de expiración (YYYY-MM-DD).")
@click.option("--tier", default="pro", help="Nivel: trial/pro/enterprise.")
@click.option("--secret", required=True, help="Clave secreta para firmar la licencia.")
def generate_license(machine_id: str, expires: str | None, tier: str, secret: str) -> None:
    """Genera una licencia firmada (uso interno del licensor)."""
    from lbamonitor.core.services.license_engine import generate_license as gen
    lic = gen(machine_id=machine_id, expires=expires, tier=tier, secret=secret)
    console.print(f"[green]Licencia generada:[/]")
    console.print(lic)


def main() -> int:
    cli()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
