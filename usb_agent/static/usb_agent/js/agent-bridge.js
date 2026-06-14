(function () {
  'use strict';

  function localBase(port) {
    return 'http://127.0.0.1:' + port;
  }

  async function checkLocal(port) {
    try {
      var response = await fetch(localBase(port) + '/health', { mode: 'cors' });
      if (!response.ok) return { running: false };
      var data = await response.json();
      if (!data || !data.ok) return { running: false };
      return {
        running: true,
        portal_paired: Boolean(data.portal_paired),
        portal_connected: Boolean(data.portal_connected),
        version: data.version || '',
      };
    } catch (err) {
      return { running: false };
    }
  }

  async function signJob(port, jobId, siteUrl, signToken) {
    var response = await fetch(localBase(port) + '/sign', {
      method: 'POST',
      mode: 'cors',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId, sign_token: signToken }),
    });
    var data = await response.json().catch(function () { return {}; });
    if (!response.ok) {
      throw new Error(data.error || 'Local agent could not sign this job.');
    }
    return data;
  }

  window.IGAgentBridge = {
    checkLocal: checkLocal,
    signJob: signJob,
  };
})();
