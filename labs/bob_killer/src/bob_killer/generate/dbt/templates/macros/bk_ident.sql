{# The one identifier quoting function of generated SQL (§3.5). #}
{% macro bk_ident(name) -%}
{{ adapter.quote(name) }}
{%- endmacro %}
