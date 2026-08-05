PRAGMA foreign_keys = ON;


INSERT INTO proxy_tags (id, name, description, owner, creation_date, tag)
    SELECT id, COALESCE(name, 'group'), COALESCE(description, ''), owner, creation_date, COALESCE(tag, '')
    FROM proxy_groups;

INSERT OR REPLACE INTO sqlite_sequence (name, seq)
    SELECT 'proxy_tags', MAX(id) FROM proxy_tags;



ALTER TABLE proxies RENAME TO proxies_old;

CREATE TABLE proxies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    avatar_url TEXT NOT NULL,
    triggers TEXT NOT NULL,
    owner INTEGER NOT NULL,
    times_used INTEGER,
    creation_date REAL,
    nickname TEXT,
    proxy_forms TEXT,
    current_form TEXT,
    pronouns TEXT,
    FOREIGN KEY (owner) REFERENCES users (user_id) ON DELETE CASCADE
);

INSERT INTO proxies (
    id, name, description, avatar_url, triggers, owner, times_used, creation_date,
    nickname, proxy_forms, current_form, pronouns
) SELECT
    id, name, COALESCE(description, ''), avatar_url, trigger, owner, times_used,
    creation_date, nickname, proxy_forms, current_form, pronouns
FROM proxies_old;

INSERT OR REPLACE INTO sqlite_sequence (name, seq)
    SELECT 'proxies', MAX(id) FROM proxies;



WITH RECURSIVE group_hierarchy (proxy_id, group_id) AS (
    SELECT p.id, p.proxy_group FROM proxies_old p WHERE p.proxy_group IS NOT NULL
    UNION ALL
        SELECT gh.proxy_id, pg.parent FROM group_hierarchy gh
            INNER JOIN proxy_groups pg ON pg.id = gh.group_id WHERE pg.parent IS NOT NULL
)
INSERT OR IGNORE INTO proxy_tags_map (proxy_id, tag_id)
    SELECT DISTINCT proxy_id, group_id FROM group_hierarchy WHERE group_id IS NOT NULL;


DROP TABLE proxies_old;
DROP TABLE proxy_groups;



ALTER TABLE message_links RENAME TO message_links_old;

CREATE TABLE message_links (
    message_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    proxy_id INTEGER,
    platform_user INTEGER,
    platform_type INTEGER,
    FOREIGN KEY (proxy_id) REFERENCES proxies(id) ON DELETE SET NULL
);
INSERT INTO message_links SELECT * FROM message_links_old;

DROP TABLE message_links_old;



ALTER TABLE user_settings RENAME TO user_settings_old;

CREATE TABLE user_settings (
    user_id INTEGER PRIMARY KEY,
    private_description BOOLEAN,
    private_trigger BOOLEAN,
    private_metadata BOOLEAN,
    private_proxy_tags BOOLEAN,
    private_list BOOLEAN,
    private_forms BOOLEAN,
    private_spotlight BOOLEAN,
    private_pronouns BOOLEAN,
    spotlight TEXT,
    dice_functions BLOB,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

INSERT INTO user_settings (
    user_id,
    private_description,
    private_trigger,
    private_metadata,
    private_proxy_tags,
    private_list,
    private_forms,
    private_spotlight,
    private_pronouns,
    spotlight,
    dice_functions
)
SELECT
    user_id,
    private_description,
    private_trigger,
    private_metadata,
    private_group,
    private_list,
    private_forms,
    private_spotlight,
    private_pronouns,
    spotlight,
    dice_functions
FROM user_settings_old;

DROP TABLE user_settings_old;



ALTER TABLE autoproxies RENAME TO autoproxies_old;

CREATE TABLE autoproxies (
    guild_id INTEGER,
    user_id INTEGER,
    proxy INTEGER,
    last_used_proxy INTEGER,
    expires REAL,
    guild_type INTEGER,
    flags INTEGER,
    PRIMARY KEY (guild_id, user_id, guild_type),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

INSERT INTO autoproxies
SELECT *
FROM autoproxies_old;

DROP TABLE autoproxies_old;

DROP INDEX IF EXISTS idx_proxies_group;
DROP INDEX IF EXISTS idx_group_parent;

UPDATE global_stats SET value = 18 WHERE key = 'version';
