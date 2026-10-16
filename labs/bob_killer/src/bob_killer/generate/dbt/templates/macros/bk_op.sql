{# The qualified Python UDF of one Excel operator, OP_<NAME> in runtime/ (§4.4). #}
{% macro bk_op(name) -%}
{{ var('bk_host_schema') }}.BK_OP_{{ name | upper }}
{%- endmacro %}
