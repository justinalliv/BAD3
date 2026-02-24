# SANG (Django Project)

If you cloned this project and get an error like `No module named mysql` or MySQL driver errors, install project dependencies first.

## 1) Create and activate a virtual environment

### macOS/Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Windows (PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

## 2) Install requirements

Run this from the folder where `manage.py` is located:

```bash
pip install -r requirements.txt
```

## 3) Configure database

This project uses MySQL in `SANG/settings.py` (`django.db.backends.mysql`), so you must have a running MySQL server and create the database:

- Database name: `sangapp_db`
- Host: `127.0.0.1`
- Port: `3306`
- User: `root`
- Password: *(empty by default in settings)*

If your local MySQL credentials are different, update `DATABASES` in `SANG/settings.py`.

## 4) Run migrations and start server

```bash
python manage.py migrate
python manage.py runserver
```

## Why this fixes the error

The project uses `PyMySQL` as the MySQL driver (`pymysql.install_as_MySQLdb()`), and it must be installed in your virtual environment before starting Django.
