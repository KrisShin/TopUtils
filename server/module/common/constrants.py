from config.settings import BASE_DIR

DEFALT_PASSWORD = '122333'
DEBUG_PASSWORD = 'd98090ecd7cd2e712addac90'

STATIC_STATIC_PATH = BASE_DIR / 'statics'
AVATAR_STATIC_PATH = STATIC_STATIC_PATH / 'avatar'
EXPORT_STATIC_PARH = STATIC_STATIC_PATH / 'export'
UPLOAD_STATIC_PARH = STATIC_STATIC_PATH / 'upload'

ROLE_STAFF = 1  # 员工
ROLE_ADMIN = 2  # 管理员
ROLE_CLIENT = 3  # 外部用户/客户
ROLE_SEPARATED = 4  # 已离职

PROJECT_FIELD_MAPPING = {
    'name': '项目名称',
    'description': '项目描述',
    'category': '项目类型',
    'target_workday': '计划人天',
    'actual_workday': '结算人天',
    'status': '项目状态',
    'progress': '项目进度',
    'start_date': '开始日期',
    'end_date': '结束日期',
}

TASK_FIELD_MAPPING = {
    'name': '任务名称',
    'project': '关联项目',
    'parent': '上级任务',
    'description': '任务描述',
    'level': '任务等级',
    'target_workday': '计划人天',
    'status': '任务状态',
    'period': '时间节点',
    'period_type': '时间节点类型',
    'progress': '任务进度',
    'progress_workday': '进度人天',
    'period_evaluation': '阶段评价',
    'period_evaluation_log': '阶段评价记录',
    'week_avg_evaluation': '综合周评',
    'actual_workday': '结算人天',
    'executors': '执行人',
}

SEPARATOR = '&' * 8

LAZY_LOAD_SIZE = 10  # table lazy load default size

# temp remove lazy load
FIRST_LOAD_SIZE = 99  # table without pagination first default size
