-- Bootstrap the cfg_app_users table in BigQuery.
--
-- This table is manually maintained (not a dbt seed) so that operational
-- user-access changes do not require a code deploy.
--
-- Run once to create the table and seed initial users:
--   bq query --use_legacy_sql=false < scripts/bootstrap_app_users.sql
--
-- To add a user later:
--   INSERT INTO `gads-export-all.gads_reporting_cfg.cfg_app_users`
--     (email, client_id, account_id, role, is_active)
--   VALUES ('user@example.com', 'client_x', '__all__', 'viewer', true);
--
-- To revoke access:
--   UPDATE `gads-export-all.gads_reporting_cfg.cfg_app_users`
--   SET is_active = FALSE
--   WHERE email = 'user@example.com';

CREATE TABLE IF NOT EXISTS `gads-export-all.gads_reporting_cfg.cfg_app_users` (
  email STRING NOT NULL,
  client_id STRING NOT NULL,
  account_id STRING NOT NULL,
  role STRING NOT NULL,
  is_active BOOL NOT NULL
);

-- Initial users: agency admin and test viewer
MERGE `gads-export-all.gads_reporting_cfg.cfg_app_users` AS target
USING (
  SELECT 'blago@idconsult.bg' AS email, '__all__' AS client_id, '__all__' AS account_id, 'admin' AS role, TRUE AS is_active
  UNION ALL
  SELECT 'biordanov@gmail.com', 'sexwell', '__all__', 'viewer', TRUE
) AS source
ON target.email = source.email AND target.client_id = source.client_id
WHEN NOT MATCHED THEN
  INSERT (email, client_id, account_id, role, is_active)
  VALUES (source.email, source.client_id, source.account_id, source.role, source.is_active);
