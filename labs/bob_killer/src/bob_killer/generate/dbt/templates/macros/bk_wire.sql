{# Seeds and vars hold wire JSON text; this builds the VARIANT wire object (D21). #}
{% macro bk_wire(text_column) -%}
PARSE_JSON({{ text_column }})
{%- endmacro %}

{% macro bk_blank() -%}
OBJECT_CONSTRUCT('k', 'z')
{%- endmacro %}
