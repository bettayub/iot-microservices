from flask import request
from flask_restx import Resource, Namespace, reqparse
from app.cylinder_registry.models import GasCylinder, UserGasUsage
from app.device_data_registry.models import DeviceData
from app.device_registry.models import Device
from app.paired_devices_registry.models import PairedDevice
from app.user_management.models import User
from common.db import db

api = Namespace('gas', description='Gas cylinder management')

change_cylinder_parser = reqparse.RequestParser()
change_cylinder_parser.add_argument('cylinder_id', type=str, required=True, help='The ID of the new gas cylinder')



@api.route('/cylinder/add')
class AddGasCylinder(Resource):
    def post(self):
        data = request.json
        cylinder_type = data.get('cylinder_type')
        empty_weight = data.get('empty_weight')
        full_weight = data.get('full_weight')

        if not all([cylinder_type, empty_weight, full_weight]):
            return {"status": "error", "message": "All fields are required: cylinder_type, empty_weight, full_weight"}, 400

        try:
            # Create a new gas cylinder entry
            cylinder = GasCylinder(
                cylinder_type=cylinder_type,
                empty_weight=empty_weight,
                full_weight=full_weight
            )
            db.session.add(cylinder)
            db.session.commit()

            return {"status": "success", "message": f"Gas Cylinder {cylinder_type} added successfully!"}, 201
        except Exception as e:
            db.session.rollback()
            return {"status": "error", "message": f"An error occurred: {str(e)}"}, 500


@api.route('/user/<string:user_id>/assign-cylinder')
class AssignCylinderToUser(Resource):
    def post(self, user_id):
        data = request.json
        cylinder_type = data.get('cylinder_type')
        current_gas_weight = data.get('current_gas_weight')

        if not cylinder_type or current_gas_weight is None:
            return {"status": "error", "message": "cylinder_type and current_gas_weight are required"}, 400

        try:
            # Fetch the user and cylinder
            user = User.query.get(user_id)
            cylinder = GasCylinder.query.filter_by(cylinder_type=cylinder_type).first()

            if not user:
                return {"status": "error", "message": f"User with ID {user_id} not found"}, 404

            if not cylinder:
                return {"status": "error", "message": f"Cylinder with type {cylinder_type} not found"}, 404

            # Create and assign UserGasUsage
            user_gas_usage = UserGasUsage(
                user_id=user.id,
                cylinder_id=cylinder.id,
                current_gas_weight=current_gas_weight
            )
            db.session.add(user_gas_usage)
            db.session.commit()

            return {"status": "success", "message": f"Cylinder {cylinder_type} assigned to user {user_id}"}, 200

        except Exception as e:
            db.session.rollback()
            return {"status": "error", "message": f"An error occurred: {str(e)}"}, 500


@api.route('/user/<string:user_id>/update-cylinder')
class UpdateUserCylinder(Resource):
    def post(self, user_id):
        data = request.json
        new_cylinder_type = data.get('cylinder_type')
        new_current_gas_weight = data.get('current_gas_weight')

        if not new_cylinder_type or new_current_gas_weight is None:
            return {"status": "error", "message": "cylinder_type and current_gas_weight are required"}, 400

        try:
            # Fetch user's current gas usage entry
            user_gas_usage = UserGasUsage.query.filter_by(user_id=user_id).first()

            if not user_gas_usage:
                return {"status": "error", "message": f"UserGasUsage for user {user_id} not found"}, 404

            # Fetch new cylinder
            new_cylinder = GasCylinder.query.filter_by(cylinder_type=new_cylinder_type).first()
            if not new_cylinder:
                return {"status": "error", "message": f"New cylinder {new_cylinder_type} not found"}, 404

            # Update the gas usage
            user_gas_usage.cylinder_id = new_cylinder.id
            user_gas_usage.current_gas_weight = new_current_gas_weight
            db.session.commit()

            return {"status": "success", "message": f"User {user_id} switched to cylinder {new_cylinder_type}"}, 200

        except Exception as e:
            db.session.rollback()
            return {"status": "error", "message": f"An error occurred: {str(e)}"}, 500

@api.route('/user/<string:user_id>')
class GetUserData(Resource):
    def get(self, user_id):
        try:
            # Fetch the user
            user = User.query.get(user_id)
            if not user:
                api.abort(404, f"User with ID {user_id} not found")

            # Fetch all paired devices for the user
            paired_devices = PairedDevice.query.filter_by(user_id=user_id).all()
            result = []

            # Fetch the user's gas usage and associated cylinder
            user_gas_usage = UserGasUsage.query.filter_by(user_id=user_id).first()

            if not user_gas_usage:
                return {"status": "error", "message": "No gas usage found for the user"}, 404

            cylinder = GasCylinder.query.get(user_gas_usage.cylinder_id)

            if not cylinder:
                return {"status": "error", "message": "No gas cylinder found"}, 404

            for paired_device in paired_devices:
                device = Device.query.filter_by(matx_id=paired_device.matx_id).first()
                if device:
                    # Fetch the latest device data
                    latest_device_data = DeviceData.query.filter_by(wall_adapter_id=device.wall_adapter_id).order_by(DeviceData.timestamp.desc()).first()

                    if latest_device_data:
                        # Decode the binary data
                        byte_data = latest_device_data.data
                        current_gas_weight = int(byte_data[7:8].hex(), 16)  # Extract weight from data

                        # Calculate remaining gas
                        remaining_gas = latest_device_data.calculate_remaining_gas(current_gas_weight, cylinder)

                        result.append({
                            'device_id': device.wall_adapter_id,
                            'device_name': paired_device.name,
                            'remaining_gas': remaining_gas if remaining_gas is not None else "Data Unavailable",
                            'cylinder_type': cylinder.cylinder_type,
                            'last_updated': latest_device_data.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                        })

            return {"status": "success", "data": result}, 200

        except Exception as e:
            return {"status": "error", "message": str(e)}, 500