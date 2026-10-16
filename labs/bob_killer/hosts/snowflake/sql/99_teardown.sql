-- Drop one deployment schema and everything in it (tables, stage, procedures, app).
-- Usage: 99_teardown.sql <schema>   (the <% schema %> variable; for example TEST_1A2B3C4D)
-- Run as BOB_KILLER_OWNER in database BOB_KILLER. Never pass APP unless you mean to remove production.
DROP SCHEMA IF EXISTS IDENTIFIER('BOB_KILLER.<% schema %>');
