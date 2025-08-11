from django import template

from django.utils.html import escape

register = template.Library()


@register.simple_block_tag
def blockescape(content) -> str:
    return escape(content)
