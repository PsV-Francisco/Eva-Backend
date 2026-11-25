from django.core.paginator import Paginator


def paginate_queryset(request, queryset, *, default_ordering, allowed_ordering, per_page=20):
    """Apply safe user ordering and preserve all filters while paginating."""
    sort = request.GET.get('sort', '')
    direction = request.GET.get('dir', 'asc').lower()
    field = allowed_ordering.get(sort, default_ordering)
    ordering = field if direction != 'desc' else f'-{field}'
    queryset = queryset.order_by(ordering)
    page_obj = Paginator(queryset, per_page).get_page(request.GET.get('page'))
    query = request.GET.copy()
    query.pop('page', None)
    return page_obj, queryset.count(), query.urlencode(), sort, direction
