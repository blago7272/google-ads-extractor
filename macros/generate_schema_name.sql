{% macro _dev_schema_owner() -%}
    {{ env_var('DBT_DEV_SCHEMA_OWNER', env_var('USER', 'local')) | lower | replace(' ', '_') | replace('-', '_') | replace('.', '_') }}
{%- endmacro %}

{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set base_schema = (custom_schema_name or target.schema) | trim -%}

    {%- if target.name == 'prod' -%}
        {{ base_schema }}
    {%- elif target.name == 'stage' -%}
        {%- if base_schema.endswith('_stage') -%}
            {{ base_schema }}
        {%- else -%}
            {{ base_schema ~ '_stage' }}
        {%- endif -%}
    {%- elif target.name == 'dev' -%}
        {%- if '_dev_' in base_schema -%}
            {{ base_schema }}
        {%- else -%}
            {{ base_schema ~ '_dev_' ~ _dev_schema_owner() }}
        {%- endif -%}
    {%- else -%}
        {{ base_schema ~ '_' ~ target.name }}
    {%- endif -%}
{%- endmacro %}
