from .models import NewsPost, SiteConfiguration


def site_content(_request):
    return {
        'site_config': SiteConfiguration.current(),
        'latest_news': NewsPost.objects.filter(published=True)[:5],
    }
