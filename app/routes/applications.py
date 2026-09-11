from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, get_db
from app.database.models import User
from app.gateway.schemas import GatewayResult, MAX_APPLICATION_ID, NoArguments
from app.gateway.service import execute_tool


router = APIRouter(
    prefix="/applications",
    tags=["材料权限演示"],
    responses={403: {"model": GatewayResult, "description": "网关拒绝访问，或材料不存在"}},
)


def gateway_response(result: GatewayResult) -> GatewayResult | JSONResponse:
    if result.decision == "ALLOW":
        return result
    status = {"NOT_AUTHENTICATED": 401, "INVALID_ARGUMENTS": 422}.get(result.reason_code, 403)
    return JSONResponse(status_code=status, content=result.model_dump())


@router.get("", response_model=GatewayResult, summary="列出我有权访问的材料编号和标题")
def list_applications(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    query: Annotated[NoArguments, Query()],
):
    request.state.gateway_started = True
    return gateway_response(execute_tool(
        db, current_user_id=user.id, tool_name="list_applications", arguments=query.model_dump(),
        request_id=request.state.request_id,
        cipher=request.app.state.field_encryption,
    ))


@router.get("/{application_id}", response_model=GatewayResult, summary="经网关授权后解密并读取一份材料正文")
def read_application(
    request: Request,
    application_id: Annotated[int, Path(gt=0, le=MAX_APPLICATION_ID, description="材料编号；与用户编号是两个独立概念")],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    query: Annotated[NoArguments, Query()],
):
    request.state.gateway_started = True
    return gateway_response(execute_tool(
        db, current_user_id=user.id, tool_name="read_application",
        arguments={"application_id": application_id},
        request_id=request.state.request_id,
        cipher=request.app.state.field_encryption,
    ))
