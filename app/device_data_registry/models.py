# device_data_registry models
import logging
import uuid
from datetime import datetime
from app.cylinder_registry.models import GasCylinder, UserGasUsage
from common.db import db

class DeviceData(db.Model):
    __tablename__ = 'device_data'

    id = db.Column(db.Integer, primary_key=True)
    wall_adapter_id = db.Column(db.String(50), nullable=False)
    gas_device_id = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.String(36), nullable=False)
    matx_id = db.Column(db.String(36), nullable=False)
    data = db.Column(db.LargeBinary)  # Binary data from the device
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, wall_adapter_id, gas_device_id, user_id, matx_id, data):
        self.wall_adapter_id = wall_adapter_id
        self.gas_device_id = gas_device_id
        self.user_id = user_id
        self.matx_id = matx_id
        self.data = data

    def calculate_remaining_gas(self, current_weight, cylinder):
        """
        Calculate remaining gas based on the cylinder's empty and full weight
        and the current gas weight reported by the device.
        """
        if current_weight is None or current_weight == 0:
            return None
        
        remaining_gas = current_weight - cylinder.empty_weight
        return max(0, remaining_gas)  # Ensure we don’t have negative values

    def update_gas_usage(self, new_weight):
        """
        This method updates the gas usage data for the user, checks for refills, and adjusts the refill count.
        """
        try:
            user_gas_usage = UserGasUsage.query.filter_by(user_id=self.user_id).first()

            if not user_gas_usage:
                return

            # Convert the new weight to a float
            new_weight_float = float(new_weight)

            # Get previous gas weight
            previous_weight = user_gas_usage.current_gas_weight
            cylinder = GasCylinder.query.get(user_gas_usage.cylinder_id)

            if not cylinder:
                return

            # Check if the gas weight increased significantly (e.g., after a refill)
            near_empty_threshold = 0.5  # Can be adjusted based on cylinder type
            full_weight = cylinder.full_weight

            # If the previous weight was below the near-empty threshold and the new weight is close to the full weight
            if previous_weight <= near_empty_threshold and new_weight_float >= (full_weight - 0.5):
                # Update refill count
                user_gas_usage.refill_count += 1
                print(f"Refill detected for user {self.user_id}. Refill count incremented.")

            # Update current weight
            user_gas_usage.current_gas_weight = new_weight_float

            # Commit changes
            db.session.commit()

        except Exception as e:
            logging.error(f"Error updating gas usage: {str(e)}")
            db.session.rollback()