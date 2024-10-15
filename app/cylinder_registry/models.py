
from datetime import datetime
from common.db import db

class GasCylinder(db.Model):
    __tablename__ = 'gas_cylinders'

    id = db.Column(db.Integer, primary_key=True)
    cylinder_type = db.Column(db.String(50), nullable=False)  # e.g., "6 kg", "13 kg"
    empty_weight = db.Column(db.Float, nullable=False)  # in kg
    full_weight = db.Column(db.Float, nullable=False)  # in kg
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, cylinder_type, empty_weight, full_weight):
        self.cylinder_type = cylinder_type
        self.empty_weight = empty_weight
        self.full_weight = full_weight


class UserGasUsage(db.Model):
    __tablename__ = 'user_gas_usage' 

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    cylinder_id = db.Column(db.Integer, db.ForeignKey('gas_cylinders.id'), nullable=False)  # Change to Integer
    current_gas_weight = db.Column(db.Float, nullable=False)  # Tracks the current gas weight
    refills_count = db.Column(db.Integer, default=0)  # Number of refills done by the user
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref='gas_usage')
    cylinder = db.relationship('GasCylinder', backref='users')

    def __init__(self, user_id, cylinder_id, current_gas_weight):
        self.user_id = user_id
        self.cylinder_id = cylinder_id
        self.current_gas_weight = current_gas_weight
