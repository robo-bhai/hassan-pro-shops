from django import template

register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    """Gets a value from a dictionary given a key string or variable."""
    if isinstance(dictionary, dict):
        return dictionary.get(key, '')
    return ''

