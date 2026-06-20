(function () {
  'use strict';

  function readConfig(id) {
    var node = document.getElementById(id);
    if (!node) return null;
    return node.dataset;
  }

  function initAgentStatus() {
    var config = readConfig('usb-agent-status-config');
    if (!config || !window.IGAgentBridge) return;

    var port = parseInt(config.agentPort || '0', 10);
    var targetId = config.statusTarget || 'usb-agent-status';
    window.IGAgentBridge.checkLocal(port).then(function (status) {
      var el = document.getElementById(targetId);
      if (!el) return;
      if (!status.running) {
        el.textContent = config.messageOffline || 'Start IG E-Sign Agent on this computer before signing.';
        el.style.color = 'var(--warning)';
        return;
      }
      if (!status.portal_paired || !status.portal_connected) {
        el.textContent = config.messageUnpaired || 'Local agent is running but not connected to the portal.';
        el.style.color = 'var(--warning)';
        return;
      }
      el.textContent = config.messageReady || 'Local agent ready.';
      el.style.color = 'var(--success)';
    });
  }

  function initAgentConsole() {
    var config = readConfig('usb-agent-console-config');
    if (!config || !window.IGAgentBridge) return;

    var port = parseInt(config.agentPort || '0', 10);
    window.IGAgentBridge.checkLocal(port).then(function (status) {
      var el = document.getElementById('agent-local-status');
      if (!el) return;
      if (!status.running) {
        el.textContent = 'Local agent not detected. Install and start IG E-Sign Agent.';
        el.style.color = 'var(--text-secondary)';
        return;
      }
      if (!status.portal_paired) {
        el.textContent = 'Local agent is running but not paired. Open IG E-Sign Agent and enter a new pairing code.';
        el.style.color = 'var(--warning, #d97706)';
        return;
      }
      if (!status.portal_connected) {
        el.textContent = 'Local agent is running but offline from the portal. Re-pair in the agent window if this device was revoked.';
        el.style.color = 'var(--warning, #d97706)';
        return;
      }
      el.textContent = 'Local agent is running and connected to the portal.';
      el.style.color = 'var(--success)';
    });

    var form = document.getElementById('agent-pair-form');
    if (!form) return;
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      fetch(form.action, {
        method: 'POST',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value,
        },
      }).then(function (response) {
        return response.json();
      }).then(function (data) {
        var box = document.getElementById('pairing-code-box');
        if (!box) return;
        box.style.display = 'block';
        box.textContent = 'Pairing code: ' + data.code + ' (expires soon)';
      });
    });
  }

  function initUsbSignPending() {
    var config = readConfig('usb-sign-pending-config');
    if (!config || !window.IGAgentBridge) return;

    var statusEl = document.getElementById('usb-sign-status');
    var port = parseInt(config.agentPort || '0', 10);
    var pollTimer = null;
    var signingStarted = false;

    function stopPolling() {
      if (pollTimer !== null) {
        clearTimeout(pollTimer);
        pollTimer = null;
      }
    }

    function showError(message) {
      stopPolling();
      if (!statusEl) return;
      statusEl.textContent = message;
      statusEl.style.color = 'var(--danger, #b91c1c)';
    }

    function handleTerminalStatus(data) {
      if (data.status === 'completed') {
        stopPolling();
        window.location.href = config.doneUrl;
        return true;
      }
      if (data.status === 'failed') {
        showError(data.error || 'Signing failed.');
        return true;
      }
      if (data.status === 'expired') {
        showError('Signing job expired. Upload the PDF and try again.');
        return true;
      }
      return false;
    }

    function pollStatus() {
      return fetch(config.statusUrl, { credentials: 'same-origin' }).then(function (response) {
        return response.json();
      });
    }

    function schedulePoll(delayMs) {
      stopPolling();
      pollTimer = setTimeout(function () {
        pollStatus().then(function (data) {
          if (handleTerminalStatus(data)) {
            return;
          }
          if (statusEl) {
            statusEl.textContent = 'Waiting for agent to complete…';
          }
          schedulePoll(2000);
        }).catch(function () {
          schedulePoll(3000);
        });
      }, delayMs);
    }

    function fetchAgentToken() {
      return fetch(config.tokenUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'X-CSRFToken': config.csrfToken || '',
          'X-Requested-With': 'XMLHttpRequest',
        },
      }).then(function (response) {
        if (!response.ok) {
          return response.json().then(function (body) {
            throw new Error(body.error || 'Could not fetch sign token.');
          });
        }
        return response.json();
      });
    }

    function resolveLocalFailure(err) {
      return pollStatus().then(function (data) {
        if (handleTerminalStatus(data)) {
          return;
        }
        showError(
          (err && err.message) ||
            'Signing was cancelled or could not complete. Start IG E-Sign Agent and try again.',
        );
      }).catch(function () {
        showError(
          (err && err.message) ||
            'Signing was cancelled or could not complete. Start IG E-Sign Agent and try again.',
        );
      });
    }

    function startSigning() {
      if (signingStarted) return;
      signingStarted = true;
      if (statusEl) {
        statusEl.textContent = 'Waiting for local agent…';
        statusEl.style.color = 'var(--text-secondary)';
      }

      fetchAgentToken()
        .then(function (tokenPayload) {
          return window.IGAgentBridge.signJob(
            port,
            config.jobId,
            config.siteUrl,
            tokenPayload.sign_token,
          );
        })
        .then(function () {
          if (statusEl) statusEl.textContent = 'Agent reported success. Finalizing…';
          schedulePoll(500);
        })
        .catch(function (err) {
          resolveLocalFailure(err);
        });
    }

    startSigning();
  }

  document.addEventListener('DOMContentLoaded', function () {
    initAgentStatus();
    initAgentConsole();
    initUsbSignPending();
  });
})();
