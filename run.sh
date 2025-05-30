git pull
aerich upgrade
# gunicorn -c gunicorn_config.py main:app
gunicorn -c gunicorn_config.py main:app --daemon