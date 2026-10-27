-- Drop one deployment schema and everything in it (tables, stage, procedures, app), and every
-- run output schema of it (<schema>__R_<run id>, the dbt targets).
-- Usage: 99_teardown.sql <schema>   (the <% schema %> variable; for example TEST_1A2B3C4D)
-- Run as BOB_KILLER_OWNER in database BOB_KILLER. Never pass APP unless you mean to remove production.
EXECUTE IMMEDIATE $$
DECLARE
  run_schemas CURSOR FOR
    SELECT schema_name FROM BOB_KILLER.INFORMATION_SCHEMA.SCHEMATA
    WHERE schema_name LIKE '<% schema %>__R_%' AND STARTSWITH(schema_name, '<% schema %>__R_');
BEGIN
  FOR s IN run_schemas DO
    EXECUTE IMMEDIATE 'DROP SCHEMA IF EXISTS IDENTIFIER(''BOB_KILLER."' || s.schema_name || '"'')';
  END FOR;
END;
$$;
DROP SCHEMA IF EXISTS IDENTIFIER('BOB_KILLER.<% schema %>');
