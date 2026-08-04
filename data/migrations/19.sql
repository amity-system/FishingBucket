UPDATE proxies SET nickname = '' WHERE nickname IS NULL;
UPDATE proxies SET proxy_forms = '{}' WHERE proxy_forms IS NULL;
UPDATE proxies SET current_form = '' WHERE current_form IS NULL;
UPDATE proxies SET pronouns = '' WHERE pronouns IS NULL;

UPDATE proxy_tags SET description = '' WHERE description IS NULL;
UPDATE proxy_tags SET tag = '' WHERE tag IS NULL;

UPDATE global_stats SET value = 19 WHERE key = 'version';
