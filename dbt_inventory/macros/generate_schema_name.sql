-- Use the configured custom schema verbatim (STAGING / MARTS) instead of
-- dbt's default <target_schema>_<custom_schema> concatenation.
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim | upper }}
    {%- endif -%}
{%- endmacro %}
