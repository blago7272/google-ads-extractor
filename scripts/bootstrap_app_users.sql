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
--
-- To subscribe a user to Telegram notifications, set their chat id (nullable;
-- app/telegram_bot.py only pushes to rows where it is non-NULL):
--   UPDATE `gads-export-all.gads_reporting_cfg.cfg_app_users`
--   SET telegram_chat_id = 123456789
--   WHERE email = 'user@example.com';
--
-- Note: CREATE TABLE IF NOT EXISTS will not add telegram_chat_id to a table
-- that predates it. On an existing deployment run:
--   ALTER TABLE `gads-export-all.gads_reporting_cfg.cfg_app_users`
--   ADD COLUMN IF NOT EXISTS telegram_chat_id INT64;
--
-- One chat id, one message. A person legitimately owns many rows here -- the
-- grain is (email, client_id, account_id), so a viewer with twelve accounts has
-- twelve rows -- and the same human may also hold both an admin and a viewer
-- profile under two different emails. Neither case may produce two daily
-- summaries in the same Telegram chat.
--
-- The bot enforces this in code, not by trusting the data:
-- get_telegram_users() collapses rows to one record per email, and
-- push_daily_summary() then collapses records to one per telegram_chat_id,
-- sorting admins first so the broadest scope wins. Interactive commands resolve
-- the same way via _find_user_by_chat_id(). Duplicate rows are therefore safe;
-- they are just untidy.
--
-- To see which chat ids are shared across more than one email:
--   SELECT telegram_chat_id, COUNT(DISTINCT email) AS emails,
--          STRING_AGG(DISTINCT email) AS email_list
--   FROM `gads-export-all.gads_reporting_cfg.cfg_app_users`
--   WHERE telegram_chat_id IS NOT NULL AND is_active = TRUE
--   GROUP BY telegram_chat_id HAVING COUNT(DISTINCT email) > 1;
--
-- To tidy one up, clear the chat id on the narrower profile rather than
-- deleting the row -- the row still grants dashboard access, it just stops
-- being a notification target. Keep the admin profile as the subscriber:
--   UPDATE `gads-export-all.gads_reporting_cfg.cfg_app_users`
--   SET telegram_chat_id = NULL
--   WHERE email = 'biordanov@gmail.com' AND telegram_chat_id = 1945218457;
--
-- That statement has been APPLIED to prod (3 rows: the ITF, matraci.bg and
-- sexwell viewer grants). Chat id 1945218457 now resolves to the admin profile
-- blago@idconsult.bg alone, whose __all__/__all__ scope is a superset of the
-- three cleared grants, so the summary lost no accounts. Every active chat id
-- in the table now maps to exactly one email.

CREATE TABLE IF NOT EXISTS `gads-export-all.gads_reporting_cfg.cfg_app_users` (
  email STRING NOT NULL,
  client_id STRING NOT NULL,
  account_id STRING NOT NULL,
  role STRING NOT NULL,
  is_active BOOL NOT NULL,
  telegram_chat_id INT64
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
