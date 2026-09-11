from sqlalchemy import false, select, true
from sqlalchemy.sql.elements import ColumnElement

from app.database.models import AdvisorAssignment, Application, User


def visible_application_filter(user: User) -> ColumnElement[bool]:
    """返回数据库查询条件，让列表与单份材料共用同一套规则。"""
    if user.role == "student":
        return Application.owner_id == user.id
    if user.role == "advisor":
        assigned_students = select(AdvisorAssignment.student_id).where(
            AdvisorAssignment.advisor_id == user.id,
        )
        return Application.owner_id.in_(assigned_students)
    if user.role == "admin":
        return true()
    # 默认拒绝：未来新增角色也不会自动获得权限。
    return false()
