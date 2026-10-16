{# The qualified Python UDF of one runtime function (D20, §4.4). Arguments follow the call. #}
{% macro bk_fn(name) -%}
{{ var('bk_host_schema') }}.BK_FN_{{ name | replace('.', '_') | upper }}
{%- endmacro %}
