from accounts.safe_throttle import FailClosedSimpleRateThrottle, SafeSimpleRateThrottle


class AgentPairThrottle(SafeSimpleRateThrottle):
    scope = 'agent_pair'

    def get_cache_key(self, request, view):
        return f'throttle_agent_pair_{self.get_ident(request)}'


class AgentHeartbeatThrottle(FailClosedSimpleRateThrottle):
    scope = 'agent_heartbeat'

    def get_cache_key(self, request, view):
        device = request.auth
        if device is not None:
            return f'throttle_agent_hb_{device.prefix}'
        return f'throttle_agent_hb_ip_{self.get_ident(request)}'


class AgentJobThrottle(FailClosedSimpleRateThrottle):
    scope = 'agent_job'

    def get_cache_key(self, request, view):
        device = request.auth
        if device is not None:
            return f'throttle_agent_job_{device.prefix}'
        return f'throttle_agent_job_ip_{self.get_ident(request)}'
