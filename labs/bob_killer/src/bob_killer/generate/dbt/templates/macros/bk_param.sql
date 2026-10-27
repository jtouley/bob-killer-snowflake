{# A promoted parameter as a wire object; the var holds float.hex() text (D21). #}
{% macro bk_param(id) -%}
OBJECT_CONSTRUCT('k', 'n', 'h', '{{ var("p_" ~ id) }}')
{%- endmacro %}
