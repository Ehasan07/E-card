from django import template

register = template.Library()

@register.filter
def multiply(value, arg):
    return value * arg

@register.filter
def modulo(value, arg):
    return value % arg

@register.filter
def index(list_value, arg):
    try:
        return list_value[arg]
    except (IndexError, TypeError):
        return None