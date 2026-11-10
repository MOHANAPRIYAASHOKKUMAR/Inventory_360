-- Safe division returning NULL when the denominator is zero
{% macro safe_divide(numerator, denominator) -%}
    ({{ numerator }}) / NULLIF(({{ denominator }}), 0)
{%- endmacro %}

-- UK financial year label (April - March), e.g. FY25/26
{% macro uk_fiscal_year(date_col) -%}
    'FY' || RIGHT(TO_VARCHAR(YEAR(DATEADD(month, -3, {{ date_col }}))), 2)
         || '/' || RIGHT(TO_VARCHAR(YEAR(DATEADD(month, -3, {{ date_col }})) + 1), 2)
{%- endmacro %}
