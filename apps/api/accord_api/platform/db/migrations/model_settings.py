from accord_api.platform.db import database as store


def initialize():
    store.execute("""CREATE TABLE IF NOT EXISTS accord_model_preferences (
        unit_id TEXT PRIMARY KEY, reasoning_effort TEXT NOT NULL,
        selected_model TEXT NOT NULL DEFAULT '')""")
    columns = {
        row['name'] for row in store.connection().execute('PRAGMA table_info(accord_model_preferences)')
    }
    if 'selected_model' not in columns:
        store.connection().execute(
            "ALTER TABLE accord_model_preferences ADD COLUMN selected_model TEXT NOT NULL DEFAULT ''"
        )
