"""
Cliente HTTP singleton para la API de LBAMonitor v4.3.

Características:
- Usa `requests` para simplicidad sincrónica (Qt calling thread)
- Gestiona access_token + refresh_token JWT
- Inyecta header `Authorization: Bearer <access_token>` en cada request
- Maneja 401 con refresh automático (POST /api/auth/refresh)
- Lanza excepciones con código HTTP legible para que la UI las muestre
"""
from __future__ import annotations

from typing import Any, Optional

import requests


class APIError(Exception):
    """Error de API con código HTTP y detalle."""

    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail
        super().__init__(f"HTTP {status}: {detail}")


class ApiClient:
    """Cliente HTTP que añade JWT automáticamente a todas las peticiones."""

    def __init__(self, base_url: str = "http://127.0.0.1:8123") -> None:
        self.base_url = base_url.rstrip("/")
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        # Metadatos del usuario logueado
        self.user_id: Optional[int] = None
        self.username: Optional[str] = None
        self.role: Optional[str] = None
        # Mutex para evitar loops infinitos de refresh
        self._refreshing = False
        # Sesión requests para reusar conexiones
        self._session = requests.Session()
        self._timeout = 10  # segundos

    # ------------------------------------------------------------------
    # Setters / Getters
    # ------------------------------------------------------------------

    def set_tokens(self, access_token: str, refresh_token: str = "") -> None:
        self._access_token = access_token
        if refresh_token:
            self._refresh_token = refresh_token

    def get_access_token(self) -> Optional[str]:
        return self._access_token

    def get_refresh_token(self) -> Optional[str]:
        return self._refresh_token

    def clear_tokens(self) -> None:
        self._access_token = None
        self._refresh_token = None
        self.user_id = None
        self.username = None
        self.role = None

    @property
    def is_authenticated(self) -> bool:
        return self._access_token is not None

    # ------------------------------------------------------------------
    # Login / Refresh / Logout
    # ------------------------------------------------------------------

    def login(self, username: str, password: str) -> dict:
        """
        Hace POST /api/auth/login con {username, password} y guarda tokens.

        Devuelve la respuesta JSON completa:
            {access_token, refresh_token, token_type, expires_in,
             user_id, username, role}

        Lanza APIError(401) si credenciales inválidas.
        """
        url = f"{self.base_url}/api/auth/login"
        resp = self._session.post(
            url,
            json={"username": username, "password": password},
            timeout=self._timeout,
        )
        if resp.status_code != 200:
            raise APIError(resp.status_code, self._extract_detail(resp))

        data = resp.json()
        self._access_token = data.get("access_token")
        self._refresh_token = data.get("refresh_token")
        self.user_id = data.get("user_id")
        self.username = data.get("username")
        self.role = data.get("role")
        return data

    def _do_refresh(self) -> bool:
        """
        Llama a POST /api/auth/refresh con el refresh_token actual.

        Devuelve True si el refresh fue exitoso, False en caso contrario.
        Mutación: si tiene éxito, actualiza access_token y refresh_token.
        """
        if not self._refresh_token:
            return False
        try:
            resp = self._session.post(
                f"{self.base_url}/api/auth/refresh",
                json={"refresh_token": self._refresh_token},
                timeout=self._timeout,
            )
        except requests.RequestException:
            return False
        if resp.status_code != 200:
            # Refresh token inválido/expirado → logout forzado
            self.clear_tokens()
            return False
        data = resp.json()
        self._access_token = data.get("access_token")
        self._refresh_token = data.get("refresh_token")
        # user_id puede no estar en respuestas de refresh antiguas
        if data.get("user_id") is not None:
            self.user_id = data["user_id"]
        return True

    def logout(self) -> None:
        """Limpia tokens locales. Best-effort: notifica al backend si puede."""
        if self._access_token:
            try:
                self._session.post(
                    f"{self.base_url}/api/auth/logout",
                    json={"token": self._access_token},
                    timeout=self._timeout,
                )
            except requests.RequestException:
                pass
        self.clear_tokens()

    # ------------------------------------------------------------------
    # Core _request (con refresh-on-401)
    # ------------------------------------------------------------------

    def _headers(self, extra: dict | None = None) -> dict:
        h = {"Accept": "application/json"}
        if self._access_token:
            h["Authorization"] = f"Bearer {self._access_token}"
        if extra:
            h.update(extra)
        return h

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: Any = None,
        data: Any = None,
        files: Any = None,
        extra_headers: dict | None = None,
        _retry: bool = True,
    ) -> Any:
        url = f"{self.base_url}{path}"
        headers = self._headers(extra_headers)
        # Si se envía JSON, añadir Content-Type; si se envían files, no (lo
        # gestiona requests automáticamente)
        if json_body is not None and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        try:
            resp = self._session.request(
                method,
                url,
                params=params,
                json=json_body if json_body is not None else None,
                data=data,
                files=files,
                headers=headers,
                timeout=self._timeout,
            )
        except requests.ConnectionError as e:
            raise APIError(0, f"No se pudo conectar a {self.base_url}: {e}")
        except requests.Timeout:
            raise APIError(0, f"Timeout conectando a {self.base_url}")
        except requests.RequestException as e:
            raise APIError(0, str(e))

        # 401 → intentar refresh una sola vez
        if resp.status_code == 401 and _retry and self._refresh_token and not self._refreshing:
            self._refreshing = True
            try:
                ok = self._do_refresh()
            finally:
                self._refreshing = False
            if ok:
                return self._request(
                    method,
                    path,
                    params=params,
                    json_body=json_body,
                    data=data,
                    files=files,
                    extra_headers=extra_headers,
                    _retry=False,  # no reintentar de nuevo
                )
            # Refresh falló → propagar 401
            raise APIError(401, "Sesión expirada. Inicie sesión de nuevo.")

        if resp.status_code >= 400:
            raise APIError(resp.status_code, self._extract_detail(resp))

        # 204 No Content o body vacío
        if resp.status_code == 204 or not resp.content:
            return {}
        # Intentar parsear JSON; si falla, devolver texto
        try:
            return resp.json()
        except ValueError:
            return resp.text

    @staticmethod
    def _extract_detail(resp: requests.Response) -> str:
        try:
            data = resp.json()
            if isinstance(data, dict):
                # FastAPI error: {"detail": "..."}
                detail = data.get("detail")
                if isinstance(detail, str):
                    return detail
                return str(detail) if detail is not None else resp.text
            return str(data)
        except ValueError:
            return resp.text or resp.reason

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def get(self, path: str, params: dict | None = None, **kw) -> Any:
        return self._request("GET", path, params=params, **kw)

    def post(self, path: str, data: Any = None, **kw) -> Any:
        # Para compatibilidad con llamadas estilo post(path, dict)
        if isinstance(data, dict) and "json_body" not in kw:
            return self._request("POST", path, json_body=data, **kw)
        return self._request("POST", path, json_body=data, **kw)

    def put(self, path: str, data: Any = None, **kw) -> Any:
        if isinstance(data, dict) and "json_body" not in kw:
            return self._request("PUT", path, json_body=data, **kw)
        return self._request("PUT", path, json_body=data, **kw)

    def patch(self, path: str, data: Any = None, **kw) -> Any:
        if isinstance(data, dict) and "json_body" not in kw:
            return self._request("PATCH", path, json_body=data, **kw)
        return self._request("PATCH", path, json_body=data, **kw)

    def delete(self, path: str, **kw) -> Any:
        return self._request("DELETE", path, **kw)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def is_api_responding(self) -> bool:
        """Verifica que el backend responda (no requiere auth)."""
        try:
            self._session.get(
                f"{self.base_url}/api/health/ping",
                timeout=3,
            )
            return True
        except Exception:
            return False


# ─────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────

_client: ApiClient | None = None


def get_client() -> ApiClient:
    global _client
    if _client is None:
        _client = ApiClient()
    return _client


def set_client(client: ApiClient) -> None:
    """Permite inyectar un ApiClient preconfigurado (ej. con base_url distinta)."""
    global _client
    _client = client
