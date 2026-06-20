"""GST portal UI metadata — business-friendly labels for the lookup console."""

from __future__ import annotations

from typing import Any

from accounts.api_docs_catalog import build_service_catalog, flatten_catalog_items, personalize_catalog_defaults

GST_ENDPOINT_ORDER = [
    'gst-gstin-search',
    'gst-preference',
    'gst-return-status',
    'gst-eway-print',
    'gst-irn-print',
]

GST_PRINT_ENDPOINTS = frozenset({'gst-eway-print', 'gst-irn-print'})

PORTAL_UI: dict[str, dict[str, Any]] = {
    'gst-gstin-search': {
        'tab': 'GSTIN details',
        'heading': 'Look up taxpayer details',
        'lead': 'View registration status and business information for a GSTIN on the GST network.',
        'action': 'Look up GSTIN',
        'fields': {
            'gstin': {
                'label': 'GSTIN',
                'hint': 'Leave blank to use your profile GSTIN, or enter any GSTIN to look up.',
                'placeholder': 'e.g. 33AAUPP8709M3ZS',
            },
        },
    },
    'gst-preference': {
        'tab': 'Filing preferences',
        'heading': 'Check filing preferences',
        'lead': 'See how returns are configured for a financial year — useful before filing season.',
        'action': 'Check preferences',
        'fields': {
            'fy': {
                'label': 'Financial year',
                'hint': 'Format: 2024-25',
                'placeholder': '2024-25',
            },
            'gstin': {
                'label': 'GSTIN',
                'hint': 'Leave blank to use your profile GSTIN, or enter any GSTIN to look up.',
                'placeholder': 'e.g. 33AAUPP8709M3ZS',
            },
        },
    },
    'gst-return-status': {
        'tab': 'Return status',
        'heading': 'Check return filing status',
        'lead': 'Find out whether GSTR-1, GSTR-3B, or GSTR-9 has been filed for a financial year.',
        'action': 'Check status',
        'fields': {
            'fy': {
                'label': 'Financial year',
                'hint': 'Format: 2024-25',
                'placeholder': '2024-25',
            },
            'type': {
                'label': 'Return type',
                'hint': 'Optional — leave as “All returns” to see every type.',
                'options': [
                    {'value': '', 'label': 'All returns'},
                    {'value': 'R1', 'label': 'GSTR-1'},
                    {'value': 'R3B', 'label': 'GSTR-3B'},
                    {'value': 'R9', 'label': 'GSTR-9'},
                ],
            },
            'gstin': {
                'label': 'GSTIN',
                'hint': 'Leave blank to use your profile GSTIN, or enter any GSTIN to look up.',
                'placeholder': 'e.g. 33AAUPP8709M3ZS',
            },
        },
    },
    'gst-eway-print': {
        'tab': 'E-WAY bill',
        'heading': 'Print E-WAY bill',
        'lead': 'Download the detailed E-WAY bill PDF using the GSTIN and NIC portal credentials on your company profile.',
        'action': 'Download PDF',
        'fields': {
            'ewbNumber': {
                'label': 'E-way bill number',
                'hint': '12-digit E-WAY bill number.',
                'placeholder': 'e.g. 123456789012',
            },
        },
    },
    'gst-irn-print': {
        'tab': 'E-invoice IRN',
        'heading': 'Print e-invoice (IRN)',
        'lead': 'Download the e-invoice PDF using the GSTIN and NIC portal credentials on your company profile.',
        'action': 'Download PDF',
        'fields': {
            'irn': {
                'label': 'IRN',
                'hint': '64-character hexadecimal Invoice Reference Number.',
                'placeholder': '64-character IRN',
            },
        },
    },
}

RETURN_TYPE_LABELS = {'R1': 'GSTR-1', 'R3B': 'GSTR-3B', 'R9': 'GSTR-9'}


def build_gst_portal_endpoints(
    base_url: str,
    *,
    gstin: str = '',
    fy: str = '2024-25',
) -> dict[str, Any]:
    catalog = build_service_catalog(base_url, ['gst'])
    catalog = personalize_catalog_defaults(catalog, gstin=gstin, fy=fy)
    items_by_id = {
        item['id']: item
        for item in flatten_catalog_items(catalog)
        if item.get('kind') == 'endpoint'
    }
    endpoints = []
    for endpoint_id in GST_ENDPOINT_ORDER:
        item = items_by_id.get(endpoint_id)
        if not item:
            continue
        ui = PORTAL_UI.get(item['id'], {})
        fields_ui = ui.get('fields', {})
        parameters = []
        for param in item.get('parameters', []):
            if param['name'] not in fields_ui:
                continue
            meta = fields_ui[param['name']]
            parameters.append(
                {
                    **param,
                    'label': meta.get('label', param['name']),
                    'hint': meta.get('hint', ''),
                    'placeholder': meta.get('placeholder', ''),
                    'options': meta.get('options'),
                }
            )
        endpoints.append(
            {
                'id': item['id'],
                'title': item['title'],
                'ui': ui,
                'parameters': parameters,
            }
        )
    return {
        'defaults': catalog.get('defaults', {}),
        'endpoints': endpoints,
    }
