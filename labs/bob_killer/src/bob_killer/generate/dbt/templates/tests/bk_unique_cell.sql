{# IR keys: one row per cell and a value on every row. No dbt package (D28). #}
{% test bk_unique_cell(model) %}
SELECT
    {{ bk_ident('sheet') }} AS cell_sheet,
    {{ bk_ident('row') }} AS cell_row,
    {{ bk_ident('col') }} AS cell_col,
    COUNT(*) AS rows_for_cell
FROM {{ model }}
GROUP BY 1, 2, 3
HAVING COUNT(*) > 1
UNION ALL
SELECT {{ bk_ident('sheet') }}, {{ bk_ident('row') }}, {{ bk_ident('col') }}, 0
FROM {{ model }}
WHERE {{ bk_ident('value') }} IS NULL
{% endtest %}
