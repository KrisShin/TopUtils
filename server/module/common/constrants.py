from config.settings import BASE_DIR

DEFALT_PASSWORD = 'ffffuck'
DEBUG_PASSWORD = '49b4e29241ed58d8b6bc1d84bf7c8593'

STATIC_STATIC_PATH = BASE_DIR / 'statics'
AVATAR_STATIC_PATH = STATIC_STATIC_PATH / 'avatar'
EXPORT_STATIC_PARH = STATIC_STATIC_PATH / 'export'
UPLOAD_STATIC_PARH = STATIC_STATIC_PATH / 'upload'


SEPARATOR = '&' * 8

LAZY_LOAD_SIZE = 10  # table lazy load default size

# temp remove lazy load
FIRST_LOAD_SIZE = 99  # table without pagination first default size
