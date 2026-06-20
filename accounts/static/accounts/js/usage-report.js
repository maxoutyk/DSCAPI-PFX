(function () {
  'use strict';

  function readPayload() {
    const node = document.getElementById('usage-report-data');
    if (!node) return null;
    try {
      return JSON.parse(node.textContent);
    } catch (_error) {
      return null;
    }
  }

  function cssVar(name, fallback) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
  }

  function chartColors() {
    return {
      signing: cssVar('--accent', '#ff6600'),
      gst: cssVar('--success', '#22d3a5'),
      grid: cssVar('--border', 'rgba(255,255,255,0.08)'),
      text: cssVar('--text-secondary', '#8b8fa8'),
      palette: ['#ff6600', '#22d3a5', '#60a5fa', '#f59e0b', '#a78bfa', '#f472b6', '#34d399', '#fb7185'],
    };
  }

  function formatDayLabel(isoDate) {
    const date = new Date(`${isoDate}T00:00:00`);
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  function buildDailyChart(canvas, daily, colors) {
    const labels = daily.map((point) => formatDayLabel(point.date));
    return new Chart(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'Signing / USB',
            data: daily.map((point) => point.signing),
            backgroundColor: colors.signing,
            borderRadius: 4,
            stack: 'usage',
          },
          {
            label: 'GST',
            data: daily.map((point) => point.gst),
            backgroundColor: colors.gst,
            borderRadius: 4,
            stack: 'usage',
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            labels: { color: colors.text, boxWidth: 12, boxHeight: 12 },
          },
          tooltip: {
            callbacks: {
              footer(items) {
                const total = items.reduce((sum, item) => sum + (item.parsed.y || 0), 0);
                return `Total: ${total}`;
              },
            },
          },
        },
        scales: {
          x: {
            stacked: true,
            ticks: { color: colors.text, maxRotation: 0, autoSkipPadding: 12 },
            grid: { color: colors.grid },
          },
          y: {
            stacked: true,
            beginAtZero: true,
            ticks: { color: colors.text, precision: 0 },
            grid: { color: colors.grid },
          },
        },
      },
    });
  }

  function buildCustomerShareChart(canvas, groups, colors) {
    const active = groups.filter((group) => group.total > 0);
    return new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels: active.map((group) => group.customer_label),
        datasets: [
          {
            data: active.map((group) => group.total),
            backgroundColor: active.map((_, index) => colors.palette[index % colors.palette.length]),
            borderWidth: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom',
            labels: { color: colors.text, boxWidth: 12, boxHeight: 12 },
          },
        },
      },
    });
  }

  function downloadBaseUrl() {
    const meta = document.getElementById('usage-report-meta');
    return meta ? meta.dataset.downloadUrl : '/dashboard/usage/download/';
  }

  function selectedPeriod() {
    const meta = document.getElementById('usage-report-meta');
    return meta ? meta.dataset.period : '';
  }

  function updateCustomerDownloads(bucket) {
    const container = document.getElementById('usage-customer-downloads');
    if (!container) return;
    const base = downloadBaseUrl();
    const period = encodeURIComponent(selectedPeriod());
    const periodQuery = period ? `&period=${period}` : '';
    container.innerHTML = `
      <a class="btn btn-secondary btn-sm" href="${base}?scope=customer&bucket=${encodeURIComponent(bucket)}&format=csv${periodQuery}">Download customer CSV</a>
      <a class="btn btn-secondary btn-sm" href="${base}?scope=customer&bucket=${encodeURIComponent(bucket)}&format=pdf${periodQuery}">Download customer PDF</a>
    `;
  }

  function init() {
    const periodForm = document.getElementById('usage-period-form');
    const periodSelect = document.getElementById('usage-period-select');
    if (periodForm && periodSelect) {
      periodSelect.addEventListener('change', () => periodForm.submit());
    }

    const payload = readPayload();
    if (!payload || typeof Chart === 'undefined') return;

    const colors = chartColors();
    const dailyCanvas = document.getElementById('usage-daily-chart');
    const customerCanvas = document.getElementById('usage-customer-chart');
    const customerDailyCanvas = document.getElementById('usage-customer-daily-chart');
    const customerSelect = document.getElementById('usage-customer-select');

    if (dailyCanvas) {
      buildDailyChart(dailyCanvas, payload.daily_overall || [], colors);
    }

    if (customerCanvas) {
      buildCustomerShareChart(customerCanvas, payload.customer_groups || [], colors);
    }

    let customerDailyChart = null;
    function renderCustomerDaily(bucket) {
      const group = (payload.customer_groups || []).find((item) => item.bucket === bucket);
      if (!customerDailyCanvas || !group) return;
      if (customerDailyChart) {
        customerDailyChart.destroy();
      }
      customerDailyChart = buildDailyChart(customerDailyCanvas, group.daily || [], colors);
      updateCustomerDownloads(bucket);
    }

    if (customerSelect) {
      customerSelect.addEventListener('change', () => renderCustomerDaily(customerSelect.value));
      if (customerSelect.value) {
        renderCustomerDaily(customerSelect.value);
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
