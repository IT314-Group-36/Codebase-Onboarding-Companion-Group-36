from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Repository
from ..schemas import OnboardingTasks
from ..services.tasks import onboarding_tasks
from .deps import get_ready_repo

router = APIRouter(prefix="/api/v1/repos/{repo_id}", tags=["Onboarding"])


@router.get("/onboarding-tasks", response_model=OnboardingTasks, summary="Suggested first-week tasks")
def tasks(repo: Repository = Depends(get_ready_repo), db: Session = Depends(get_db)):
    return onboarding_tasks(db, repo)
