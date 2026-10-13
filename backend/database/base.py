"""
SQLAlchemy base classes and database configuration.
"""
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import DeclarativeBase

# Base class for all models
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass

# For compatibility with existing code
Model = declarative_base(cls=Base)