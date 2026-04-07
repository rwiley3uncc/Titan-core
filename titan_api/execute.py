from fastapi import APIRouter
from titan_core.executor import execute_action

router = APIRouter()


@router.post("/execute")
def execute(action: dict):
    return execute_action(action)