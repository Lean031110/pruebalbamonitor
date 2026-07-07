"""
GUI del Generador de Licencias LBAMonitor v4.4 — Programa aparte.

App standalone con Tkinter (Python puro, sin dependencias externas).
Para uso del LICENSOR (no del cliente).

Ejecutar:
    python -m tools.license_generator.gui

O como standalone (compilar con PyInstaller):
    pyinstaller --onefile --windowed --name "LBAMonitor-LicenseGenerator" \\
        tools/license_generator/gui.py
"""
from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# Setup path para importar lbamonitor
_BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


class LicenseGeneratorApp:
    """Aplicación GUI para generar licencias."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("LBAMonitor v4.4 — Generador de Licencias")
        self.root.geometry("700x750")
        self.root.resizable(False, False)

        # Estado
        self.license_result = tk.StringVar(value="")
        self.secret_var = tk.StringVar()
        self.private_key_path = tk.StringVar()
        self.machine_id_var = tk.StringVar()
        self.tier_var = tk.StringVar(value="pro")
        self.expires_var = tk.StringVar(
            value=(datetime.now(timezone.utc) + timedelta(days=365)).date().isoformat()
        )
        self.use_rsa_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Listo")

        self._build_ui()

    def _build_ui(self) -> None:
        # Header
        header = ttk.Frame(self.root, padding=(20, 15))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="Generador de Licencias LBAMonitor v4.4",
            font=("Arial", 16, "bold"),
        ).pack()
        ttk.Label(
            header,
            text="Programa del licensor — NO distribuir a clientes",
            font=("Arial", 9),
            foreground="red",
        ).pack()

        # Notebook para tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=20, pady=10)

        # Tab 1: Generar licencia
        gen_frame = ttk.Frame(notebook, padding=15)
        notebook.add(gen_frame, text="Generar licencia")
        self._build_generate_tab(gen_frame)

        # Tab 2: Generar keypair RSA
        key_frame = ttk.Frame(notebook, padding=15)
        notebook.add(key_frame, text="Generar claves RSA")
        self._build_keypair_tab(key_frame)

        # Tab 3: Ayuda
        help_frame = ttk.Frame(notebook, padding=15)
        notebook.add(help_frame, text="Ayuda")
        self._build_help_tab(help_frame)

        # Status bar
        status = ttk.Frame(self.root, relief="sunken", padding=(10, 5))
        status.pack(fill="x", side="bottom")
        ttk.Label(status, textvariable=self.status_var, font=("Arial", 9)).pack(side="left")

    def _build_generate_tab(self, parent: ttk.Frame) -> None:
        # Algoritmo
        algo_frame = ttk.LabelFrame(parent, text="Algoritmo de firma", padding=10)
        algo_frame.pack(fill="x", pady=(0, 10))
        ttk.Radiobutton(
            algo_frame,
            text="HMAC-SHA256 (simple, requiere secret compartido con cliente)",
            variable=self.use_rsa_var,
            value=False,
            command=self._toggle_algo,
        ).pack(anchor="w")
        ttk.Radiobutton(
            algo_frame,
            text="RSA-2048 (recomendado, más seguro, no comparte secret)",
            variable=self.use_rsa_var,
            value=True,
            command=self._toggle_algo,
        ).pack(anchor="w")

        # HMAC secret
        self.secret_frame = ttk.LabelFrame(parent, text="Secret HMAC", padding=10)
        self.secret_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(
            self.secret_frame,
            text="Debe ser el MISMO que el cliente usa en LBAMONITOR_LICENSE__SIGNING_SECRET",
            foreground="gray",
        ).pack(anchor="w")
        secret_entry = ttk.Entry(self.secret_frame, textvariable=self.secret_var, show="*", width=70)
        secret_entry.pack(fill="x", pady=2)
        ttk.Button(self.secret_frame, text="Generar secret aleatorio", command=self._gen_secret).pack(anchor="w")

        # RSA private key
        self.rsa_frame = ttk.LabelFrame(parent, text="Private key RSA", padding=10)
        # No pack aquí, se muestra solo si RSA seleccionado
        ttk.Label(
            self.rsa_frame,
            text="Archivo .pem con la private key (genérala en tab 'Generar claves RSA')",
            foreground="gray",
        ).pack(anchor="w")
        rsa_entry_row = ttk.Frame(self.rsa_frame)
        rsa_entry_row.pack(fill="x", pady=2)
        ttk.Entry(rsa_entry_row, textvariable=self.private_key_path, width=55).pack(side="left")
        ttk.Button(rsa_entry_row, text="Examinar...", command=self._browse_privkey).pack(side="left", padx=5)

        # Datos de licencia
        data_frame = ttk.LabelFrame(parent, text="Datos de la licencia", padding=10)
        data_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(data_frame, text="Machine ID del cliente (HWID):").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(data_frame, textvariable=self.machine_id_var, width=65).grid(
            row=0, column=1, sticky="w", pady=2, padx=5
        )

        ttk.Label(data_frame, text="Tier:").grid(row=1, column=0, sticky="w", pady=2)
        tier_combo = ttk.Combobox(
            data_frame,
            textvariable=self.tier_var,
            values=["trial", "pro", "enterprise"],
            state="readonly",
            width=15,
        )
        tier_combo.grid(row=1, column=1, sticky="w", pady=2, padx=5)

        ttk.Label(data_frame, text="Fecha de expiración (YYYY-MM-DD):").grid(row=2, column=0, sticky="w", pady=2)
        expires_row = ttk.Frame(data_frame)
        expires_row.grid(row=2, column=1, sticky="w", pady=2, padx=5)
        ttk.Entry(expires_row, textvariable=self.expires_var, width=20).pack(side="left")
        ttk.Button(expires_row, text="+30d", command=lambda: self._add_days(30)).pack(side="left", padx=2)
        ttk.Button(expires_row, text="+90d", command=lambda: self._add_days(90)).pack(side="left", padx=2)
        ttk.Button(expires_row, text="+1 año", command=lambda: self._add_days(365)).pack(side="left", padx=2)

        # Botón generar
        ttk.Button(parent, text="🔐 Generar licencia", command=self._generate).pack(pady=10)

        # Resultado
        result_frame = ttk.LabelFrame(parent, text="Licencia generada", padding=10)
        result_frame.pack(fill="both", expand=True)
        result_text = tk.Text(result_frame, height=8, wrap="word", font=("Courier", 9))
        result_text.pack(fill="both", expand=True)
        self.result_text = result_text

        # Botones de resultado
        btn_row = ttk.Frame(result_frame)
        btn_row.pack(fill="x", pady=5)
        ttk.Button(btn_row, text="Copiar al portapapeles", command=self._copy_result).pack(side="left", padx=2)
        ttk.Button(btn_row, text="Guardar en archivo...", command=self._save_result).pack(side="left", padx=2)
        ttk.Button(btn_row, text="Limpiar", command=self._clear_result).pack(side="left", padx=2)

    def _build_keypair_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="Generar par de claves RSA-2048",
            font=("Arial", 12, "bold"),
        ).pack(anchor="w", pady=5)

        ttk.Label(
            parent,
            text=(
                "Esto genera dos archivos:\n"
                "• private_key.pem — MANTÉN SECRETO, úsalo solo en este programa\n"
                "• public_key.pem — compártelo con el cliente, va en su backend\n\n"
                "El cliente configurará LBAMONITOR_LICENSE__PUBLIC_KEY_PEM con el contenido "
                "de public_key.pem. Tú usarás private_key.pem para firmar licencias."
            ),
            justify="left",
        ).pack(anchor="w", pady=10)

        ttk.Label(parent, text="Directorio destino:").pack(anchor="w", pady=(10, 0))
        path_row = ttk.Frame(parent)
        path_row.pack(fill="x", pady=2)
        self.keypair_dir = tk.StringVar(value=str(Path.cwd() / "keys"))
        ttk.Entry(path_row, textvariable=self.keypair_dir, width=55).pack(side="left")
        ttk.Button(path_row, text="Examinar...", command=self._browse_keypair_dir).pack(side="left", padx=5)

        ttk.Button(parent, text="🔑 Generar par de claves", command=self._gen_keypair).pack(pady=15)

        self.keypair_log = tk.Text(parent, height=12, wrap="word", font=("Courier", 9))
        self.keypair_log.pack(fill="both", expand=True)

    def _build_help_tab(self, parent: ttk.Frame) -> None:
        help_text = """LBAMonitor v4.4 — Generador de Licencias

CÓMO FUNCIONA:

1. El cliente instala LBAMonitor en su PC
2. El cliente ejecuta 'lbamonitor-cli machine-id' y obtiene su HWID (64 chars hex)
3. El cliente te envía ese HWID por WhatsApp/email
4. Tú (licensor) usas este programa para generar una licencia para ese HWID
5. Le envías la licencia al cliente
6. El cliente la pega en su app desktop (tab Licencia → Activar) o la pone en config.toml
7. La licencia se persiste en la BD del cliente
8. Cada vez que arranca, el backend verifica la licencia contra el HWID

ALGORITMOS:

• HMAC-SHA256: simple pero requiere que tú y el cliente compartan el mismo secret.
  Si alguien obtiene el secret, puede generar licencias.

• RSA-2048 (RECOMENDADO): tú tienes la private key, el cliente solo la public key.
  Aunque el cliente inspeccione su código, no puede generar licencias válidas.
  Es el algoritmo usado por sistemas profesionales.

TRIAL DE 10 DÍAS:

Sin licencia, LBAMonitor funciona en modo TRIAL por 10 días con todas las features.
Después de 10 días, entra en modo EXPIRED (solo lectura: ver historial, stats).
Para desbloquear, debe activar una licencia.

ANTI-TAMPERING:

• La fecha de primera instalación se firma con HMAC
• Si se detecta rollback de reloj, se bloquea
• La licencia incluye timestamp de emisión y HWID del cliente
• No se puede transferir una licencia entre máquinas

SEGURIDAD:

• NUNCA compartas tu private key o secret HMAC
• Guarda el private key en un lugar seguro (pendrive encriptado, gestor de contraseñas)
• Si se compromete, genera un nuevo par de claves y redistribuye la public key
"""
        text_widget = tk.Text(parent, wrap="word", font=("Arial", 10))
        text_widget.pack(fill="both", expand=True)
        text_widget.insert("1.0", help_text)
        text_widget.config(state="disabled")

    # ─── Acciones ───

    def _toggle_algo(self) -> None:
        if self.use_rsa_var.get():
            self.secret_frame.pack_forget()
            self.rsa_frame.pack(fill="x", pady=(0, 10), after=self.algo_frame) if hasattr(self, "algo_frame") else None
            # Re-empaquetar rsa_frame después del secret_frame o al principio
            self.rsa_frame.pack(fill="x", pady=(0, 10))
        else:
            self.rsa_frame.pack_forget()
            self.secret_frame.pack(fill="x", pady=(0, 10))

    def _gen_secret(self) -> None:
        import secrets
        self.secret_var.set(secrets.token_hex(32))

    def _browse_privkey(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleccionar private key",
            filetypes=[("PEM files", "*.pem"), ("All files", "*.*")],
        )
        if path:
            self.private_key_path.set(path)

    def _browse_keypair_dir(self) -> None:
        path = filedialog.askdirectory(title="Seleccionar directorio destino")
        if path:
            self.keypair_dir.set(path)

    def _add_days(self, days: int) -> None:
        try:
            current = datetime.fromisoformat(self.expires_var.get())
        except ValueError:
            current = datetime.now(timezone.utc)
        new_date = current + timedelta(days=days)
        self.expires_var.set(new_date.date().isoformat())

    def _generate(self) -> None:
        """Genera la licencia en un hilo separado."""
        machine_id = self.machine_id_var.get().strip()
        if not machine_id:
            messagebox.showerror("Error", "Machine ID es obligatorio")
            return

        if len(machine_id) < 32:
            if not messagebox.askyesno(
                "Confirmar",
                f"Machine ID parece corto ({len(machine_id)} chars). ¿Continuar?"
            ):
                return

        self.status_var.set("Generando licencia...")
        self.root.config(cursor="watch")

        def _work():
            try:
                # Setear env vars según selección
                use_rsa = self.use_rsa_var.get()
                if use_rsa:
                    priv_path = self.private_key_path.get().strip()
                    if not priv_path or not Path(priv_path).is_file():
                        raise RuntimeError("Selecciona un archivo de private key válido")
                    os.environ["LBAMONITOR_LICENSE__PRIVATE_KEY_FILE"] = priv_path
                else:
                    secret = self.secret_var.get().strip()
                    if not secret:
                        raise RuntimeError("Ingresa el secret HMAC")
                    os.environ["LBAMONITOR_LICENSE__SIGNING_SECRET"] = secret

                # Importar después de setear env
                from tools.license_generator.generate import generate_license_for_machine

                license_str = generate_license_for_machine(
                    machine_id=machine_id,
                    tier=self.tier_var.get(),
                    expires=self.expires_var.get().strip() or None,
                    use_rsa=use_rsa,
                )

                self.result_text.delete("1.0", "end")
                self.result_text.insert("1.0", license_str)
                self.status_var.set(f"✓ Licencia generada ({'RSA' if use_rsa else 'HMAC'})")

            except Exception as e:
                self.status_var.set("Error")
                messagebox.showerror("Error", str(e))
            finally:
                self.root.config(cursor="")

        threading.Thread(target=_work, daemon=True).start()

    def _gen_keypair(self) -> None:
        """Genera par de claves RSA."""
        out_dir = Path(self.keypair_dir.get())
        if not out_dir:
            messagebox.showerror("Error", "Selecciona un directorio destino")
            return

        self.status_var.set("Generando claves RSA-2048...")
        self.root.config(cursor="watch")

        def _work():
            try:
                from tools.license_generator.generate import _generate_keypair
                priv, pub = _generate_keypair(out_dir)
                self.keypair_log.delete("1.0", "end")
                self.keypair_log.insert("1.0", f"✓ Par de claves generado:\n\n")
                self.keypair_log.insert("end", f"Private key: {priv}\n")
                self.keypair_log.insert("end", f"Public key:  {pub}\n\n")
                self.keypair_log.insert("end", "INSTRUCCIONES:\n")
                self.keypair_log.insert("end", f"1. Guarda {priv.name} en lugar seguro\n")
                self.keypair_log.insert("end", f"2. Comparte {pub.name} con el cliente\n")
                self.keypair_log.insert("end", f"3. Cliente: LBAMONITOR_LICENSE__PUBLIC_KEY_PEM=$(cat {pub.name})\n")
                self.keypair_log.insert("end", f"4. Tú: LBAMONITOR_LICENSE__PRIVATE_KEY_FILE={priv}\n")
                self.status_var.set("✓ Par de claves RSA generado")
            except Exception as e:
                self.status_var.set("Error")
                messagebox.showerror("Error", str(e))
            finally:
                self.root.config(cursor="")

        threading.Thread(target=_work, daemon=True).start()

    def _copy_result(self) -> None:
        license_str = self.result_text.get("1.0", "end").strip()
        if not license_str:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(license_str)
        self.status_var.set("✓ Copiado al portapapeles")

    def _save_result(self) -> None:
        license_str = self.result_text.get("1.0", "end").strip()
        if not license_str:
            return
        path = filedialog.asksaveasfilename(
            title="Guardar licencia",
            defaultextension=".lic",
            filetypes=[("Licencia", "*.lic"), ("Texto", "*.txt"), ("All", "*.*")],
        )
        if path:
            Path(path).write_text(license_str)
            self.status_var.set(f"✓ Guardado en {path}")

    def _clear_result(self) -> None:
        self.result_text.delete("1.0", "end")
        self.status_var.set("Listo")


def main() -> int:
    root = tk.Tk()
    app = LicenseGeneratorApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
