from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Repository
from ..schemas import RepoCreate, RepoOut
from ..services.ingest import delete_repo, derive_name, index_repository, validate_source
from .deps import get_repo

router = APIRouter(prefix="/api/v1/repos", tags=["Repositories"])


@router.post("", response_model=RepoOut, status_code=202, summary="Register a repo and start indexing")
def create_repo(payload: RepoCreate, background: BackgroundTasks, db: Session = Depends(get_db)):
    source = payload.source.strip()
    try:
        validate_source(source)
    except ValueError as e:
        raise HTTPException(400, str(e))
    repo = Repository(name=payload.name or derive_name(source), source=source)
    db.add(repo)
    db.commit()
    db.refresh(repo)
    background.add_task(index_repository, repo.id)
    return repo


@router.get("", response_model=list[RepoOut], summary="List repositories")
def list_repos(db: Session = Depends(get_db)):
    return db.scalars(select(Repository).order_by(Repository.id.desc())).all()


@router.get("/{repo_id}", response_model=RepoOut, summary="Get repo + indexing status")
def read_repo(repo: Repository = Depends(get_repo)):
    return repo


@router.post("/{repo_id}/reindex", response_model=RepoOut, status_code=202, summary="Re-run indexing")
def reindex(background: BackgroundTasks, repo: Repository = Depends(get_repo), db: Session = Depends(get_db)):
    if repo.status == "indexing":
        raise HTTPException(409, "Already indexing")
    repo.status = "pending"
    db.commit()
    background.add_task(index_repository, repo.id)
    return repo


@router.delete("/{repo_id}", status_code=204, summary="Delete repo and all its indexed data")
def remove_repo(repo: Repository = Depends(get_repo), db: Session = Depends(get_db)):
    delete_repo(db, repo)
