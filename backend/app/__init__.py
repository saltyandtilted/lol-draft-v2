"""Flask application factory."""

import sqlite3

from flask import Flask, jsonify

from . import db
from .config import Config


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)

    db.init_db(app.config["DATABASE_PATH"])

    @app.get("/api/health")
    def health():
        try:
            version = db.schema_version(app.config["DATABASE_PATH"])
            db_status = "ok"
        except sqlite3.Error:
            version = None
            db_status = "error"
        return jsonify(
            status="ok",
            database=db_status,
            schema_version=version,
            # Only report whether the key is set, never its value.
            riot_api_key_configured=bool(app.config["RIOT_API_KEY"]),
        )

    return app
