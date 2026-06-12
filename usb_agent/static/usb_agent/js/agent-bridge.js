(function () {
  'use strict';

  function localBase(port) {
    return 'http://127.0.0.1:' + port;
  }

  async function checkLocal(port) {
    try {
      var response = await fetch(localBase(port) + '/health', { mode: 'cors' });
      if (!response.ok) return false;
      var data = await response.json();
      return Boolean(data && data.ok);
    } catch (err) {
      return false;
    }
  }

  async function signJob(port, jobId, siteUrl) {
    var response = await fetch(localBase(port) + '/sign', {
      method: 'POST',
      mode: 'cors',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId, api_base: siteUrl }),
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
