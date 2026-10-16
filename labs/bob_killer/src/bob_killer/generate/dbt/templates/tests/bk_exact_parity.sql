{# Exact parity (D15, §5.4): a row fails when either side is missing or the values differ. #}
{% test bk_exact_parity(model, oracle) %}
WITH expected AS (
    SELECT
        {{ bk_ident('sheet') }} AS _s,
        TO_NUMBER({{ bk_ident('row') }}) AS _r,
        TO_NUMBER({{ bk_ident('col') }}) AS _c,
        {{ bk_wire(bk_ident('wire_json')) }} AS _v
    FROM {{ ref(oracle) }}
),
actual AS (
    SELECT
        {{ bk_ident('sheet') }} AS _s,
        {{ bk_ident('row') }} AS _r,
        {{ bk_ident('col') }} AS _c,
        {{ bk_ident('value') }} AS _v
    FROM {{ model }}
)
SELECT
    COALESCE(e._s, a._s) AS cell_sheet,
    COALESCE(e._r, a._r) AS cell_row,
    COALESCE(e._c, a._c) AS cell_col,
    e._v AS expected,
    a._v AS actual
FROM expected AS e
FULL OUTER JOIN actual AS a
    ON e._s = a._s AND e._r = a._r AND e._c = a._c
WHERE e._s IS NULL
    OR a._s IS NULL
    OR NOT {{ var('bk_host_schema') }}.BK_VALUES_EQUAL(e._v, a._v)
{% endtest %}
