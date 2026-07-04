from django.http import HttpResponse

from .seo import robots_txt_lines


def robots_txt_view(request):
    body = '\n'.join(robots_txt_lines()) + '\n'
    return HttpResponse(body, content_type='text/plain; charset=utf-8')
