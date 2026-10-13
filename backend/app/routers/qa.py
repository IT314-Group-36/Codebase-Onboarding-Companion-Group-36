from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Question, Repository
from ..schemas import AskRequest, AskResponse, ImpactRequest, ImpactResponse, QuestionOut
from ..services.impact import analyze_impact
from ..services.search import answer_question
from .deps import get_ready_repo, get_repo

router = APIRouter(prefix="/api/v1/repos/{repo_id}", tags=["Ask"])


@router.post("/ask", response_model=AskResponse, summary="Ask a natural-language question about the codebase")
def ask(payload: AskRequest, repo: Repository = Depends(get_ready_repo), db: Session = Depends(get_db)):
    answer, sources, provider = answer_question(db, repo.id, payload.question)
    db.add(Question(repo_id=repo.id, question=payload.question, answer=answer,
                    sources=[s.model_dump() for s in sources]))
    db.commit()
    return AskResponse(question=payload.question, answer=answer, sources=sources, used_ai=provider is not None, provider=provider)


@router.get("/questions", response_model=list[QuestionOut], summary="Question history")
def history(limit: int = 20, repo: Repository = Depends(get_repo), db: Session = Depends(get_db)):
    return db.scalars(select(Question).where(Question.repo_id == repo.id)
                      .order_by(Question.id.desc()).limit(limit)).all()


@router.post("/impact", response_model=ImpactResponse, summary="What would break if I change this file/function?")
def impact(payload: ImpactRequest, repo: Repository = Depends(get_ready_repo), db: Session = Depends(get_db)):
    return analyze_impact(db, repo, payload.target)
