from dataclasses import dataclass, replace
from pathlib import Path

from django.conf import settings

DEFAULT_ANCHOR_TEXT = 'Authorised Signatory'


class SignatureStyleLookupError(LookupError):
    """Raised when a tenant requests a signature style that does not exist or is disabled."""


@dataclass(frozen=True)
class SignatureStyleConfig:
    """Resolved signature placement and appearance for a signing request."""

    anchor_text: str
    font_size: int
    box_min_width: int
    box_height: int
    box_right_padding: int
    box_shift_right: int
    box_gap_above_label: int
    box_shift_down_fitz: int
    box_page_margin: int
    icon_path: str | None
    icon_display_width: int
    icon_overlap_inset: int
    icon_padding: int
    is_custom: bool = False
    style_name: str | None = None

    @classmethod
    def from_settings(cls) -> 'SignatureStyleConfig':
        icon = getattr(settings, 'SIGNATURE_ICON', None)
        icon_path = str(icon) if icon and Path(icon).is_file() else None
        return cls(
            anchor_text=getattr(settings, 'SIGNATURE_ANCHOR_TEXT', DEFAULT_ANCHOR_TEXT),
            font_size=getattr(settings, 'SIGNATURE_FONT_SIZE', 8),
            box_min_width=getattr(settings, 'SIGNATURE_BOX_MIN_WIDTH', 118),
            box_height=getattr(settings, 'SIGNATURE_BOX_HEIGHT', 64),
            box_right_padding=getattr(settings, 'SIGNATURE_BOX_RIGHT_PADDING', 28),
            box_shift_right=getattr(settings, 'SIGNATURE_BOX_SHIFT_RIGHT', 15),
            box_gap_above_label=getattr(settings, 'SIGNATURE_BOX_GAP_ABOVE_LABEL', 2),
            box_shift_down_fitz=getattr(settings, 'SIGNATURE_BOX_SHIFT_DOWN_FITZ', 8),
            box_page_margin=getattr(settings, 'SIGNATURE_BOX_PAGE_MARGIN', 5),
            icon_path=icon_path,
            icon_display_width=getattr(settings, 'SIGNATURE_ICON_DISPLAY_WIDTH', 60),
            icon_overlap_inset=getattr(settings, 'SIGNATURE_ICON_OVERLAP_INSET', 20),
            icon_padding=getattr(settings, 'SIGNATURE_ICON_PADDING', 2),
            is_custom=False,
            style_name=None,
        )


def lookup_tenant_signature_style(
    tenant,
    *,
    style_name: str | None = None,
    style_id: int | None = None,
):
    styles = tenant.signature_styles.all()
    if style_id is not None:
        return styles.filter(pk=style_id).first()
    if style_name:
        normalized = style_name.strip()
        if not normalized:
            return None
        return styles.filter(name__iexact=normalized).first()
    return styles.filter(is_enabled=True, is_default=True).first()


def _merge_tenant_style(base: SignatureStyleConfig, tenant_style) -> SignatureStyleConfig:
    updates: dict = {'is_custom': True, 'style_name': tenant_style.name}
    if tenant_style.anchor_text:
        updates['anchor_text'] = tenant_style.anchor_text
    for field in (
        'font_size',
        'box_min_width',
        'box_height',
        'box_right_padding',
        'box_shift_right',
        'box_gap_above_label',
        'box_shift_down_fitz',
        'box_page_margin',
        'icon_display_width',
        'icon_overlap_inset',
        'icon_padding',
    ):
        value = getattr(tenant_style, field, None)
        if value is not None:
            updates[field] = value

    if tenant_style.custom_icon and tenant_style.custom_icon.name:
        icon_path = tenant_style.custom_icon.path
        if Path(icon_path).is_file():
            updates['icon_path'] = icon_path

    return replace(base, **updates)


def resolve_signature_style(
    tenant=None,
    *,
    style_name: str | None = None,
    style_id: int | None = None,
) -> SignatureStyleConfig:
    """
    Return global defaults unless the tenant has an enabled style to apply.

    - No tenant: platform defaults only.
    - style_name / style_id: use that style (must exist and be enabled).
    - Otherwise: tenant default style if enabled, else platform defaults.
    """
    base = SignatureStyleConfig.from_settings()
    if tenant is None:
        if style_name or style_id is not None:
            raise SignatureStyleLookupError('signature_style requires tenant API authentication.')
        return base

    explicit_request = bool(style_name or style_id is not None)
    tenant_style = lookup_tenant_signature_style(
        tenant,
        style_name=style_name,
        style_id=style_id,
    )

    if explicit_request:
        if tenant_style is None:
            label = style_name or style_id
            raise SignatureStyleLookupError(f'Signature style not found: {label!r}')
        if not tenant_style.is_enabled:
            raise SignatureStyleLookupError(f'Signature style is disabled: {tenant_style.name!r}')
        return _merge_tenant_style(base, tenant_style)

    if tenant_style is None or not tenant_style.is_enabled:
        return base

    return _merge_tenant_style(base, tenant_style)
