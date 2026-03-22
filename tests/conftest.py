"""Felles fixtures for pytest."""

import os
import tempfile

import pytest

# Sett DB_PATH til temp-fil FØR import av app/db
@pytest.fixture(autouse=True)
def test_db(tmp_path):
    db_path = str(tmp_path / 'test.db')
    os.environ['DB_PATH'] = db_path
    os.environ['SECRET_KEY'] = 'test-secret'
    os.environ['REGISTRER_KODE'] = 'testkode'
    os.environ['STATS_KEY'] = 'testkey'
    os.environ['RESEND_API_KEY'] = ''

    # Reload db-modul med ny path
    import db as db_mod
    db_mod.DB_PATH = db_path
    db_mod.init_db()
    db_mod._migrer_db()

    yield db_path


@pytest.fixture
def app(test_db):
    # Importer etter at DB_PATH er satt
    import db as db_mod
    db_mod.DB_PATH = test_db

    from server import app
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def innlogget_client(app, test_db):
    """Test-klient som er innlogget som vanlig bruker."""
    import db as db_mod
    from werkzeug.security import generate_password_hash
    db_mod.opprett_bruker('test@test.no', generate_password_hash('passord123'))

    client = app.test_client()
    client.post('/auth/logg-inn', data={
        'brukernavn': 'test@test.no',
        'passord': 'passord123',
    })
    return client


@pytest.fixture
def admin_client(app, test_db):
    """Test-klient som er innlogget som admin."""
    import db as db_mod
    from werkzeug.security import generate_password_hash
    db_mod.opprett_bruker('admin@test.no', generate_password_hash('admin123'), er_admin=True)

    client = app.test_client()
    client.post('/auth/logg-inn', data={
        'brukernavn': 'admin@test.no',
        'passord': 'admin123',
    })
    return client
