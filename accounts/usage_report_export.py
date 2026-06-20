"""CSV and PDF export for tenant usage reports."""

from __future__ import annotations

import csv
import io
from datetime import datetime

from accounts.templatetags.display_tz import DISPLAY_TZ

PDF_MIMETYPE = 'application/pdf'
CSV_MIMETYPE = 'text/csv; charset=utf-8'


def _format_period(report: dict) -> str:
    start = report['period_start_display']
    end = report['period_end_display']
    return f'{start.isoformat()} to {end.isoformat()}'


def _local_date(value):
    from datetime import date

    from django.utils import timezone

    if isinstance(value, datetime):
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.utc)
        return timezone.localtime(value, DISPLAY_TZ).date()
    if isinstance(value, date):
        return value
    return value


def _safe_filename_part(value: str) -> str:
    cleaned = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '-' for ch in value.strip().lower())
    while '--' in cleaned:
        cleaned = cleaned.replace('--', '-')
    return cleaned.strip('-') or 'report'


def usage_report_csv_bytes(report: dict, tenant, *, customer_group: dict | None = None) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    title = 'IG E-Sign Customer Usage Report' if customer_group else 'IG E-Sign Usage Report'
    writer.writerow([title])
    writer.writerow(['Organization', tenant.name])
    writer.writerow(['Period', _format_period(report)])
    writer.writerow([])

    if customer_group:
        writer.writerow(['Customer', customer_group['customer_label']])
        if customer_group.get('key_names'):
            writer.writerow(['API keys', ', '.join(customer_group['key_names'])])
        writer.writerow([])
        writer.writerow(['Summary'])
        writer.writerow(['Signing / USB', customer_group['signing_count']])
        writer.writerow(['GST', customer_group['gst_count']])
        writer.writerow(['Total', customer_group['total']])
        writer.writerow([])
        writer.writerow(['Daily usage'])
        writer.writerow(['Date', 'Signing / USB', 'GST', 'Total'])
        for point in customer_group['daily']:
            writer.writerow([point['date'], point['signing'], point['gst'], point['total']])
    else:
        writer.writerow(['Summary'])
        writer.writerow(['Signing / USB', report['total_signing']])
        writer.writerow(['GST', report['total_gst']])
        writer.writerow(['Total usage', report['total_usage']])
        if report.get('show_quota'):
            writer.writerow(['Quota consumed', report['quota_used']])
            writer.writerow(['Monthly quota', report['monthly_quota']])
        writer.writerow([])
        writer.writerow(['Daily usage'])
        writer.writerow(['Date', 'Signing / USB', 'GST', 'Total'])
        for point in report['daily_overall']:
            writer.writerow([point['date'], point['signing'], point['gst'], point['total']])
        writer.writerow([])
        writer.writerow(['Usage by customer'])
        writer.writerow(['Customer', 'API keys', 'Signing / USB', 'GST', 'Total'])
        for group in report['customer_groups']:
            keys = ', '.join(group.get('key_names') or []) or 'Portal'
            writer.writerow([
                group['customer_label'],
                keys,
                group['signing_count'],
                group['gst_count'],
                group['total'],
            ])
        writer.writerow([])
        writer.writerow(['Usage by API key'])
        writer.writerow(['Customer', 'API key', 'Prefix', 'Signing / USB', 'GST', 'Total'])
        for row in report['rows']:
            if row['total'] == 0 and row['is_portal']:
                continue
            writer.writerow([
                row['customer_label'],
                row['key_name'] if not row['is_portal'] else 'Portal',
                row['key_prefix'] if not row['is_portal'] else '',
                row['signing_count'],
                row['gst_count'],
                row['total'],
            ])

    return buffer.getvalue().encode('utf-8-sig')


def usage_report_pdf_bytes(report: dict, tenant, *, customer_group: dict | None = None) -> bytes:
    from .usage_report_pdf import build_usage_report_pdf

    return build_usage_report_pdf(report, tenant, customer_group=customer_group)


def usage_report_download_filename(report: dict, *, customer_group: dict | None = None, fmt: str) -> str:
    period = report['period_key']
    if customer_group:
        slug = _safe_filename_part(customer_group['customer_label'])
        return f'ig-esign-usage-{slug}-{period}.{fmt}'
    return f'ig-esign-usage-overall-{period}.{fmt}'


class UsageReportDownloadError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def build_usage_report_for_period(tenant, period: str | None = None) -> dict:
    from .services import build_monthly_usage_report, parse_usage_period_param

    parsed = parse_usage_period_param(period)
    if parsed:
        year, month = parsed
        return build_monthly_usage_report(tenant, year=year, month=month)
    return build_monthly_usage_report(tenant)


def build_usage_report_json(
    tenant,
    *,
    period: str | None = None,
    scope: str = 'overall',
    bucket: str = '',
    customer_label: str = '',
) -> dict:
    from .services import resolve_usage_customer_group

    report = build_usage_report_for_period(tenant, period)
    customer_group = None
    if scope == 'customer':
        customer_group = resolve_usage_customer_group(
            report,
            bucket=bucket,
            customer_label=customer_label,
        )
        if customer_group is None:
            raise UsageReportDownloadError('Customer usage report not found.', 404)
    elif scope != 'overall':
        raise UsageReportDownloadError('Unknown report scope. Use overall or customer.', 400)

    payload = {
        'organization': tenant.name,
        'period': report['period_key'],
        'period_start': report['period_start_display'].isoformat(),
        'period_end': report['period_end_display'].isoformat(),
        'scope': scope,
        'total_usage': report['total_usage'],
        'total_signing': report['total_signing'],
        'total_gst': report['total_gst'],
        'daily': customer_group['daily'] if customer_group else report['daily_overall'],
    }
    if customer_group:
        payload['customer'] = {
            'label': customer_group['customer_label'],
            'bucket': customer_group['bucket'],
            'signing_count': customer_group['signing_count'],
            'gst_count': customer_group['gst_count'],
            'total': customer_group['total'],
            'key_names': customer_group.get('key_names') or [],
        }
    else:
        payload['customer_groups'] = report['customer_groups']
        payload['api_keys'] = report['rows']
    if report.get('show_quota'):
        payload['quota_used'] = report['quota_used']
        payload['monthly_quota'] = report['monthly_quota']
    return payload


def build_usage_report_download(
    tenant,
    *,
    period: str | None = None,
    scope: str = 'overall',
    bucket: str = '',
    customer_label: str = '',
    fmt: str = 'pdf',
) -> tuple[bytes, str, str]:
    from .services import resolve_usage_customer_group

    report = build_usage_report_for_period(tenant, period)
    fmt = (fmt or 'pdf').lower()
    customer_group = None

    if scope == 'customer':
        customer_group = resolve_usage_customer_group(
            report,
            bucket=bucket,
            customer_label=customer_label,
        )
        if customer_group is None:
            raise UsageReportDownloadError('Customer usage report not found.', 404)
    elif scope != 'overall':
        raise UsageReportDownloadError('Unknown report scope. Use overall or customer.', 400)

    if fmt == 'pdf':
        payload = usage_report_pdf_bytes(report, tenant, customer_group=customer_group)
        content_type = PDF_MIMETYPE
    elif fmt == 'csv':
        payload = usage_report_csv_bytes(report, tenant, customer_group=customer_group)
        content_type = CSV_MIMETYPE
    else:
        raise UsageReportDownloadError('Unsupported format. Use pdf, csv, or json.', 400)

    filename = usage_report_download_filename(report, customer_group=customer_group, fmt=fmt)
    return payload, content_type, filename
