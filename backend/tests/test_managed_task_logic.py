"""Regression tests for task identity, difficulty gates and validation."""
import pytest
from pydantic import ValidationError
from app.api.managed_tasks import TaskCreate, TaskEdit
from app.services.task_manager import difficulty_for, normalize, similar


def test_difficulty_depends_on_completions_not_generation_attempts():
    assert [difficulty_for(i) for i in (0, 1, 2, 3, 7, 8, 25)] == [
        'easy', 'easy', 'easy', 'medium', 'medium', 'hard', 'hard']


def test_duplicate_normalization_and_close_paraphrase():
    assert normalize('Write Tests: Login!') == 'write tests login'
    assert similar('Add tests for login endpoint', 'Add tests for login endpoint!')
    assert similar('Document the API authentication flow', 'Document API authentication flow')
    assert not similar('Document the API authentication flow', 'Add tests for payment refunds')


def test_manual_task_validates_empty_and_bad_paths():
    with pytest.raises(ValidationError):
        TaskCreate(title='   ', description='Some description')
    with pytest.raises(ValidationError):
        TaskCreate(title='Write test docs', description='Some description', related_files=['../secrets.env'])
    assert TaskCreate(title='Write test docs', description='Some description',
                      related_files=['src/a.py', 'src/a.py']).related_files == ['src/a.py']
    with pytest.raises(ValidationError):
        TaskEdit(status='done')
