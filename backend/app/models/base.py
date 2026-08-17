"""SQLAlchemy declarative base. Tüm modeller buradan türer."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
