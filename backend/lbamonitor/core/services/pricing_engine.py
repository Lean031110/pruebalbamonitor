"""
Motor de cálculo de precios.

Soporta 5 modos:
  - per_gb: paga por GB copiado (price_per_gb)
  - per_mb: paga por MB copiado (price_per_mb)
  - per_file: paga por archivo copiado (price_per_file)
  - fixed: precio fijo (fixed_price)
  - custom: el operador decide (solo sugiere min_price)

Aplica descuentos en cadena (MULTIPLICATIVAMENTE, no aditivamente):
  1. Precio base (per_gb / per_mb / per_file / fixed / custom)
  2. Descuento VIP (si el cliente es VIP / discount / free / business)
  3. Descuento por empleado (si vip_type == 'employee')
  4. Descuento por nivel de membresía (bronce=0% … diamante=20%)
  5. Descuento por promoción (si promotion_enabled y no es FREE VIP)
  6. Impuesto (% sobre el subtotal)
  7. Límites min_price / max_price

Fórmula:
    precio_final = base * (1 - vip%) * (1 - emp%) * (1 - tier%) * (1 - promo%) * (1 + tax%)

Los descuentos son multiplicativos para evitar que la suma pase del 100%
y para que el orden de aplicación no afecte el resultado. El descuento total
efectivo (``discount_percent``) se calcula como:
    discount_percent = (1 - subtotal/base) * 100
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from lbamonitor.core.config import get_settings
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


@dataclass
class PriceCalculation:
    """Resultado del cálculo de precio para una sesión."""

    base_price: float = 0.0
    pricing_mode: str = "per_gb"
    # Descuentos individuales (%)
    vip_discount_percent: float = 0.0
    employee_discount_percent: float = 0.0
    tier_discount_percent: float = 0.0
    promotion_discount_percent: float = 0.0
    # Descuento total efectivo (para compatibilidad y display)
    discount_percent: float = 0.0
    discount_amount: float = 0.0
    discount_reason: Optional[str] = None
    subtotal: float = 0.0
    tax_percent: float = 0.0
    tax_amount: float = 0.0
    suggested_price: float = 0.0
    min_applied: Optional[float] = None
    max_applied: Optional[float] = None
    breakdown: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "base_price": self.base_price,
            "pricing_mode": self.pricing_mode,
            "vip_discount_percent": self.vip_discount_percent,
            "employee_discount_percent": self.employee_discount_percent,
            "tier_discount_percent": self.tier_discount_percent,
            "promotion_discount_percent": self.promotion_discount_percent,
            "discount_percent": self.discount_percent,
            "discount_amount": self.discount_amount,
            "discount_reason": self.discount_reason,
            "subtotal": self.subtotal,
            "tax_percent": self.tax_percent,
            "tax_amount": self.tax_amount,
            "suggested_price": self.suggested_price,
            "min_applied": self.min_applied,
            "max_applied": self.max_applied,
            "breakdown": self.breakdown,
        }


# VIPs que implican 100% descuento
FREE_VIP_TYPES = {"free", "never_pays", "business"}


class PricingEngine:
    """
    Motor de cálculo de precios.

    Uso:
        engine = PricingEngine()
        calc = engine.calculate(
            mode="per_gb",
            gb_copied=4.5,
            files_copied=12,
            vip_type="vip",
            tier_discount_percent=10.0,
        )
        print(calc.suggested_price)
    """

    def __init__(self) -> None:
        self._settings = get_settings().pricing

    def calculate(
        self,
        mode: Optional[str] = None,
        gb_copied: float = 0.0,
        files_copied: int = 0,
        vip_type: str = "none",
        tier_discount_percent: float = 0.0,
        promotion_enabled: Optional[bool] = None,
        promotion_discount_percent: Optional[float] = None,
        override_base_price: Optional[float] = None,
    ) -> PriceCalculation:
        """
        Calcula el precio sugerido para una sesión.

        Args:
            mode: modo de pricing (si None, usa el de config).
            gb_copied: GB copiados en la sesión.
            files_copied: archivos copiados en la sesión.
            vip_type: tipo de VIP del cliente.
            tier_discount_percent: descuento del tier de membresía (%).
            promotion_enabled: si None, usa el de config.
            promotion_discount_percent: si None, usa el de config.
            override_base_price: para modo custom o fixed override.
        """
        s = self._settings
        mode = mode or s.mode
        calc = PriceCalculation(pricing_mode=mode)

        # 1. Precio base según modo
        if mode == "per_gb":
            base = gb_copied * s.price_per_gb
            calc.breakdown["gb_copied"] = gb_copied
            calc.breakdown["price_per_gb"] = s.price_per_gb
        elif mode == "per_mb":
            mb = gb_copied * 1024
            base = mb * s.price_per_mb
            calc.breakdown["mb_copied"] = mb
            calc.breakdown["price_per_mb"] = s.price_per_mb
        elif mode == "per_file":
            base = files_copied * s.price_per_file
            calc.breakdown["files_copied"] = files_copied
            calc.breakdown["price_per_file"] = s.price_per_file
        elif mode == "fixed":
            base = override_base_price if override_base_price is not None else s.fixed_price
            calc.breakdown["fixed_price"] = base
        elif mode == "custom":
            base = override_base_price if override_base_price is not None else 0.0
            calc.breakdown["custom"] = base
        else:
            log.warning(f"Modo de pricing desconocido: {mode!r}, usando fixed")
            base = s.fixed_price
            calc.pricing_mode = "fixed"

        calc.base_price = round(base, 2)

        # 2. Descuento VIP (incluye casos free / business / never_pays / discount)
        calc.vip_discount_percent = self._vip_discount_percent(vip_type)

        # 3. Descuento por empleado (separado del VIP, multiplicativo)
        calc.employee_discount_percent = self._employee_discount_percent(vip_type)

        # 4. Descuento por tier de membresía (no aplica si el cliente ya es FREE VIP)
        if vip_type in FREE_VIP_TYPES:
            calc.tier_discount_percent = 0.0
        else:
            calc.tier_discount_percent = float(tier_discount_percent or 0.0)

        # 5. Descuento por promoción (no aplica si el cliente ya es FREE VIP)
        promo_enabled = promotion_enabled if promotion_enabled is not None else s.promotion_enabled
        promo_discount = (
            promotion_discount_percent
            if promotion_discount_percent is not None
            else s.promotion_discount_percent
        )
        if promo_enabled and promo_discount > 0 and vip_type not in FREE_VIP_TYPES:
            calc.promotion_discount_percent = float(promo_discount)
        else:
            calc.promotion_discount_percent = 0.0

        # Construir razón legible
        reasons: list[str] = []
        if calc.vip_discount_percent > 0:
            reasons.append(f"VIP: {calc.vip_discount_percent}%")
        if calc.employee_discount_percent > 0:
            reasons.append(f"Empleado: {calc.employee_discount_percent}%")
        if calc.tier_discount_percent > 0:
            reasons.append(f"Membresía: {calc.tier_discount_percent}%")
        if calc.promotion_discount_percent > 0:
            reasons.append(f"Promo: {calc.promotion_discount_percent}%")
        calc.discount_reason = " + ".join(reasons) if reasons else None

        # Aplicar descuentos MULTIPLICATIVAMENTE en cadena:
        #   subtotal = base * (1 - vip%) * (1 - emp%) * (1 - tier%) * (1 - promo%)
        factor = 1.0
        factor *= (1.0 - calc.vip_discount_percent / 100.0)
        factor *= (1.0 - calc.employee_discount_percent / 100.0)
        factor *= (1.0 - calc.tier_discount_percent / 100.0)
        factor *= (1.0 - calc.promotion_discount_percent / 100.0)
        # Evitar factor negativo por redondeo
        if factor < 0.0:
            factor = 0.0

        subtotal = calc.base_price * factor
        calc.subtotal = round(subtotal, 2)
        calc.discount_amount = round(calc.base_price - calc.subtotal, 2)

        # Descuento total efectivo (para display / retrocompatibilidad)
        if calc.base_price > 0:
            calc.discount_percent = round(
                (1.0 - calc.subtotal / calc.base_price) * 100.0, 4
            )
        else:
            calc.discount_percent = 0.0

        # 6. Impuesto (sobre el subtotal ya descontado)
        tax = get_settings().business.tax_percent
        if tax > 0:
            calc.tax_percent = tax
            calc.tax_amount = round(calc.subtotal * tax / 100.0, 2)

        # 7. Precio sugerido y límites min/max
        suggested = calc.subtotal + calc.tax_amount
        if suggested < s.min_price:
            calc.min_applied = s.min_price
            suggested = s.min_price
        elif suggested > s.max_price:
            calc.max_applied = s.max_price
            suggested = s.max_price

        calc.suggested_price = round(suggested, 2)

        calc.breakdown["factor"] = round(factor, 6)
        calc.breakdown["tax_percent"] = calc.tax_percent

        log.debug(
            f"PricingEngine: mode={mode} base={calc.base_price} "
            f"vip={calc.vip_discount_percent}% emp={calc.employee_discount_percent}% "
            f"tier={calc.tier_discount_percent}% promo={calc.promotion_discount_percent}% "
            f"subtotal={calc.subtotal} tax={calc.tax_amount} "
            f"suggested={calc.suggested_price}"
        )
        return calc

    def _vip_discount_percent(self, vip_type: str) -> float:
        """Devuelve el % de descuento VIP (incluye casos FREE / business / discount).

        No incluye el caso 'employee' (ese va por ``_employee_discount_percent``).
        """
        s = self._settings
        if vip_type in FREE_VIP_TYPES:
            return 100.0
        if vip_type == "vip":
            return s.vip_discount_percent
        if vip_type == "discount":
            return s.vip_discount_percent
        if vip_type == "blocked":
            # Bloqueado: no se permite copiar, precio 0 pero no se cobra
            return 0.0
        # 'none' o 'employee' → aquí no aplica descuento VIP
        return 0.0

    def _employee_discount_percent(self, vip_type: str) -> float:
        """Devuelve el % de descuento por empleado (solo si vip_type == 'employee')."""
        s = self._settings
        if vip_type == "employee":
            return s.employee_discount_percent
        return 0.0


# Singleton
_pricing_engine: PricingEngine | None = None


def get_pricing_engine() -> PricingEngine:
    global _pricing_engine
    if _pricing_engine is None:
        _pricing_engine = PricingEngine()
    return _pricing_engine
