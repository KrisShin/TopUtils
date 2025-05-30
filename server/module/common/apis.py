import json

from fastapi import APIRouter, Depends

from server.module.common.accepts import CreatedResponse, SuccessResponse
from server.module.common.exceptions import BadRequest
from server.module.common.global_variable import DataResponse
from server.module.common.models import DataTypeEnum, SystemParameter
from server.module.common.pydantics import SystemParameterCreatePydantic, SystemParameterUpdatePydantic
from server.module.user.models import User
from server.module.user.utils import current_user

router = APIRouter()


@router.post('/parameter/')
async def create_system_parameter(param: SystemParameterCreatePydantic, me: User = Depends(current_user)):
    is_param_exists = await SystemParameter.exists(name=param.name)
    if is_param_exists:
        raise BadRequest('参数已存在, 请勿重复创建')
    try:
        match param.data_type:
            case DataTypeEnum.STRING:
                pass
            case DataTypeEnum.INTEGER:
                int(param.data)
            case DataTypeEnum.FLOAT:
                float(param.data)
            case DataTypeEnum.JSON:
                json.loads(param.data)
            case _:
                raise Exception('')
    except:
        raise BadRequest(f'{param.data} 解析为 {param.data_type.value} 类型失败, 请检查数据')
    await SystemParameter.create(**param.model_dump())
    return CreatedResponse()


@router.put('/parameter/{param_name}/')
async def update_system_parameter(param: SystemParameterUpdatePydantic, me: User = Depends(current_user)):
    param_obj = await SystemParameter.get_or_none(name=param.name)
    if not param_obj:
        raise BadRequest('参数不存在, 请先创建')
    try:
        match param.data_type:
            case DataTypeEnum.STRING:
                pass
            case DataTypeEnum.INTEGER:
                int(param.data)
            case DataTypeEnum.FLOAT:
                float(param.data)
            case DataTypeEnum.JSON:
                json.loads(param.data)
            case _:
                raise Exception('')
        if param.description:
            param_obj.description = param.description
        param_obj.data_type = param.data_type
        param_obj.data = param.data
    except:
        raise BadRequest(f'{param.data} 解析为 {param.data_type.value} 类型失败, 请检查数据')
    await param_obj.save()
    return SuccessResponse()


@router.get('/parameter/{param_name}/')
async def get_system_parameter(param_name: str, me: User = Depends(current_user)):
    data = await SystemParameter.get_or_none(name=param_name)
    response = None
    if data:
        try:
            match data.data_type:
                case DataTypeEnum.STRING:
                    response = data.data
                case DataTypeEnum.INTEGER:
                    response = int(data.data)
                case DataTypeEnum.FLOAT:
                    response = float(data.data)
                case DataTypeEnum.JSON:
                    response = json.loads(data.data)
                case _:
                    response = None
        except:
            response = None
    return DataResponse(data=response)


@router.delete('/parameter/{param_name}/')
async def delete_system_parameter(param_name: str, me: User = Depends(current_user)):
    param_obj = await SystemParameter.get_or_none(name=param_name)
    if not param_obj:
        raise BadRequest('参数不存在, 无需删除')
    await param_obj.delete()
    return SuccessResponse()
