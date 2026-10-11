"""
OOP domain classes for DevTrack.

These are plain Python classes (not Django ORM models). Data is persisted
to JSON files by the views; these classes own validation, serialisation
and per-priority behaviour.
"""
from abc import ABC, abstractmethod
from datetime import datetime


class BaseEntity(ABC):
    """Common contract for every entity stored by DevTrack."""

    @abstractmethod
    def validate(self):
        """Raise ValueError with a human-readable message if the entity is invalid."""
        pass

    def to_dict(self):
        return {key: value for key, value in self.__dict__.items()}


class Reporter(BaseEntity):
    def __init__(self, id, name, email, team):
        self.id = id
        self.name = name
        self.email = email
        self.team = team

    def validate(self):
        if not isinstance(self.id, int) or isinstance(self.id, bool) or self.id < 1:
            raise ValueError('id must be a positive integer')
        if not self.name or not str(self.name).strip():
            raise ValueError('Name cannot be empty')
        if not self.email or '@' not in str(self.email):
            raise ValueError('Invalid email')
        if not self.team or not str(self.team).strip():
            raise ValueError('Team cannot be empty')


class Issue(BaseEntity):
    ALLOWED_STATUSES = ('open', 'in_progress', 'resolved', 'closed')
    ALLOWED_PRIORITIES = ('low', 'medium', 'high', 'critical')

    def __init__(self, id, title, description, status, priority, reporter_id,
                 created_at=None):
        self.id = id
        self.title = title
        self.description = description
        self.status = status
        self.priority = priority
        self.reporter_id = reporter_id
        self.created_at = created_at or str(datetime.now())

    def validate(self):
        if not isinstance(self.id, int) or isinstance(self.id, bool) or self.id < 1:
            raise ValueError('id must be a positive integer')
        if not self.title or not str(self.title).strip():
            raise ValueError('Title cannot be empty')
        if self.status not in self.ALLOWED_STATUSES:
            raise ValueError(
                f"Invalid status. Allowed values: {', '.join(self.ALLOWED_STATUSES)}"
            )
        if self.priority not in self.ALLOWED_PRIORITIES:
            raise ValueError(
                f"Invalid priority. Allowed values: {', '.join(self.ALLOWED_PRIORITIES)}"
            )
        if (not isinstance(self.reporter_id, int) or isinstance(self.reporter_id, bool)
                or self.reporter_id < 1):
            raise ValueError('reporter_id must be a positive integer')

    def describe(self):
        return f"{self.title} [{self.priority}]"


class CriticalIssue(Issue):
    def describe(self):
        return f"[URGENT] {self.title} — needs immediate attention"


class LowPriorityIssue(Issue):
    def describe(self):
        return f"{self.title} — low priority, handle when free"


def build_issue(**fields):
    """Factory: pick the Issue subclass that matches the priority."""
    priority = fields.get('priority')
    if priority == 'critical':
        return CriticalIssue(**fields)
    if priority == 'low':
        return LowPriorityIssue(**fields)
    return Issue(**fields)
