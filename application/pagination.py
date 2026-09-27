import base64

def encode_cursor(cursor):
    return base64.urlsafe_b64encode(str(cursor).encode()).decode() if cursor is not None else None

def decode_cursor(cursor_str):
    try:
        return base64.urlsafe_b64decode(cursor_str.encode()).decode()
    except Exception:
        return None

def paginate_queryset(request, queryset, cursor_key='id', limit=10, max_limit=100, is_desc=True):
    """
    Keyset/Cursor pagination supporting 'after' (next page) and 'before' (previous page) cursors.
    Assumes queryset is already ordered in the default desired order.
    """
    try:
        req_limit = int(request.GET.get('limit', limit))
        limit = min(max(1, req_limit), max_limit)
    except ValueError:
        limit = 10

    after_str = request.GET.get('after')
    before_str = request.GET.get('before')
    
    after_val = decode_cursor(after_str)
    before_val = decode_cursor(before_str)

    qs = queryset
    
    is_fetching_previous = False

    if before_val:
        # Fetching previous page
        is_fetching_previous = True
        filter_kwargs = {}
        if is_desc:
            filter_kwargs[f'{cursor_key}__gt'] = before_val
            qs = qs.filter(**filter_kwargs).order_by(cursor_key) # Reverse order for fetch
        else:
            filter_kwargs[f'{cursor_key}__lt'] = before_val
            qs = qs.filter(**filter_kwargs).order_by(f'-{cursor_key}') # Reverse order for fetch
    elif after_val:
        # Fetching next page
        filter_kwargs = {}
        if is_desc:
            filter_kwargs[f'{cursor_key}__lt'] = after_val
        else:
            filter_kwargs[f'{cursor_key}__gt'] = after_val
        qs = qs.filter(**filter_kwargs)
        
    # Fetch limit + 1 to know if there's more data in this direction
    items = list(qs[:limit + 1])
    
    has_more = len(items) > limit
    if has_more:
        items = items[:limit]

    if is_fetching_previous:
        items.reverse() # Reverse back to original desired order
        
        has_previous = has_more
        # If we fetched previous, we definitely have a next page (the one we came from)
        has_next = True 
    else:
        has_next = has_more
        # If we fetched next, we definitely have a previous page
        has_previous = bool(after_val) 

    if not items:
        # Empty result
        return {
            'items': [],
            'has_next': False,
            'has_previous': False,
            'next_url': None,
            'prev_url': None,
        }
        
    first_item_cursor = getattr(items[0], cursor_key)
    last_item_cursor = getattr(items[-1], cursor_key)
    
    base_url = request.path
    
    # Build Next URL
    next_url = None
    if has_next:
        q = request.GET.copy()
        q.pop('before', None)
        q['after'] = encode_cursor(last_item_cursor)
        q['limit'] = limit
        next_url = f"{base_url}?{q.urlencode()}"
        
    # Build Prev URL
    prev_url = None
    if has_previous:
        q = request.GET.copy()
        q.pop('after', None)
        q['before'] = encode_cursor(first_item_cursor)
        q['limit'] = limit
        prev_url = f"{base_url}?{q.urlencode()}"
        
    return {
        'items': items,
        'has_next': has_next,
        'has_previous': has_previous,
        'next_url': next_url,
        'prev_url': prev_url,
        'limit': limit,
    }
