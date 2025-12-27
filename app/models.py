from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    storage_quota = Column(Integer, default=10485760)  # 10 MB in bytes (configurable)
    storage_used = Column(Integer, default=0)  # Bytes used


class File(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    uploader = Column(String)
    size = Column(Integer)
    file_hash = Column(String)
    is_duplicate = Column(Boolean)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    folder = Column(String, nullable=True)


class Share(Base):
    __tablename__ = "shares"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer)
    share_token = Column(String, unique=True, index=True)
    created_by = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    download_count = Column(Integer, default=0)


class SharedFile(Base):
    __tablename__ = "shared_files"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer)
    shared_by = Column(String)
    shared_with = Column(String)
    shared_at = Column(DateTime, default=datetime.utcnow)


class Folder(Base):
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    owner = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class RateLimit(Base):
    __tablename__ = "rate_limits"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    endpoint = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
