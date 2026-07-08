from .distribution import microsoft_store_agent_url


def agent_downloads(request):
    return {
        'agent_microsoft_store_url': microsoft_store_agent_url(),
    }
