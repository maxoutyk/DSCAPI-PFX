from accounts.safe_throttle import SafeSimpleRateThrottle


class AgentPairThrottle(SafeSimpleRateThrottle):
    scope = 'agent_pair'

    def get_cache_key(self, request, view):
        return f'throttle_agent_pair_{self.get_ident(request)}'
