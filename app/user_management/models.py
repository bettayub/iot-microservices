from datetime import datetime
import random
import string
from sqlalchemy import Enum
from sqlalchemy.dialects.postgresql import UUID
from common.db import db
import uuid6


def generate_id():
    """Generate a 36-character UUID v7 user ID"""
    return str(uuid6.uuid7())

class User(db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_id)
    email = db.Column(db.String(120), unique=True, nullable=False)
    user_type = db.Column(Enum('customer', 'business', name='user_type_enum'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    # Relationships
    paired_devices = db.relationship('PairedDevice', back_populates='user')
    logs = db.relationship('UserLog', backref='user', lazy=True)

    def to_dict(self):
        """Convert User to a dictionary representation."""
        return {
            'id': self.id,
            'email': self.email,
            'user_type': self.user_type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
# OTP Model
class OTP(db.Model):
    __tablename__ = 'otp'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    otp = db.Column(db.String(6), nullable=False)
    action = db.Column(db.String(36), nullable=False)  # 'register' or 'login'
    user_type = db.Column(db.String(20), nullable=True)  # User type (customer or business)
    channel = db.Column(db.String(50), nullable=True)  # Channel type (e.g., 'web', 'mobile')
    user_agent = db.Column(db.String(255), nullable=True)  # User-Agent details
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expired_at = db.Column(db.DateTime, nullable=False)
    is_valid = db.Column(db.Boolean, default=True)
    attempt_count = db.Column(db.Integer, default=0)  # Track OTP request attempts

    def is_expired(self):
        return datetime.utcnow() > self.expired_at

    def increment_attempt(self):
        self.attempt_count += 1
        db.session.commit()

    def invalidate(self):
        self.is_valid = False
        db.session.commit()


# UserLog Model
class UserLog(db.Model):
    __tablename__ = 'user_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=True) 
    email = db.Column(db.String(120), nullable=False)  # New field to log user email
    action = db.Column(db.String(50), nullable=False)
    channel = db.Column(db.String(50), nullable=True)
    user_agent = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, user_id, email, action, channel, user_agent):
        self.user_id = user_id
        self.email = email
        self.action = action
        self.channel = channel
        self.user_agent = user_agent

    def to_dict(self):
        """Convert UserLog to a dictionary representation."""
        return {
            'id': self.id,
            'user_id': str(self.user_id) if self.user_id else None,
            'email': self.email,
            'action': self.action,
            'channel': self.channel,
            'user_agent': self.user_agent,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }