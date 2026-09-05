"""Compatibility entrypoint for existing launchd processes: accord_api.app:app."""

from accord_api.main import app as app
from accord_api.main import create_app as create_app
