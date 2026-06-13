from rest_framework.throttling import SimpleRateThrottle


class AgentPairThrottle(SimpleRateThrottle):
    scope = 'agent_pair'

    def get_cache_key(self, request, view):
        return f'throttle_agent_pair_{self.get_ident(request)}'
