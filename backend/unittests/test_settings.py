from backend.config.settings import Settings


def test_cors_origins_list_splits_and_strips_whitespace():
    s = Settings(CORS_ORIGINS="http://a.com, http://b.com ,http://c.com")
    assert s.cors_origins_list == ["http://a.com", "http://b.com", "http://c.com"]


def test_cors_origins_list_drops_empty_entries():
    s = Settings(CORS_ORIGINS="http://a.com,,  ,http://b.com")
    assert s.cors_origins_list == ["http://a.com", "http://b.com"]


def test_cors_origins_list_single_origin():
    s = Settings(CORS_ORIGINS="http://localhost:5173")
    assert s.cors_origins_list == ["http://localhost:5173"]


def test_database_url_built_from_parts():
    s = Settings(DB_USER="postgres", DB_PASSWORD="secret", DB_HOST="dbhost", DB_PORT=5432, DB_NAME="investigation_ai")
    assert s.DATABASE_URL == "postgresql://postgres:secret@dbhost:5432/investigation_ai"


def test_database_url_quotes_special_characters_in_credentials():
    s = Settings(DB_USER="user@corp", DB_PASSWORD="p@ss:word/!", DB_HOST="dbhost", DB_PORT=5432, DB_NAME="investigation_ai")
    assert "user%40corp" in s.DATABASE_URL
    assert "p%40ss%3Aword%2F%21" in s.DATABASE_URL


def test_database_url_override_takes_precedence():
    s = Settings(
        DATABASE_URL_OVERRIDE="postgresql://custom/conn",
        DB_USER="ignored",
        DB_PASSWORD="ignored",
    )
    assert s.DATABASE_URL == "postgresql://custom/conn"
