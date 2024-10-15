
# device_data_registry routes
from datetime import datetime, timedelta
from flask import request # type: ignore
from flask_restx import Namespace, Resource # type: ignore
from psycopg2 import IntegrityError # type: ignore
from app.notification_registry.models import DeviceEventLog
from app.notification_registry.routes import send_offline_notification, send_reminder_notification
from app.paired_devices_registry.models import PairedDevice
from app.user_management.models import User
from common.db import db
from app.device_registry.models import Device
from app.device_data_registry.models import DeviceData
import logging
import struct

api = Namespace('data', description='Device Data operations')

# Configure logging
logging.basicConfig(level=logging.ERROR, format='%(asctime)s %(levelname)s: %(message)s')


# Helper function to check if the first notification should be sent (0-15 minutes)# Helper function to check if the first notification should be sent (0-15 minutes)
def can_send_first_notification(device_id):
    """Check if the first notification can be sent for the given device ID."""
    current_time = datetime.utcnow()
    device_id = str(device_id)
    
    last_log = DeviceEventLog.query.filter_by(device_id=device_id, end_timestamp=None).first()
    
    if last_log:
        offline_duration = current_time - last_log.start_timestamp
        # Send first notification if offline for <= 15 minutes and not sent yet
        if offline_duration <= timedelta(minutes=15) and last_log.offline_message_count < 1:
            return True
    return False

# Helper function to check if the second notification should be sent (after 60 minutes)
def can_send_second_notification(device_id):
    """Check if the second notification can be sent for the given device ID."""
    current_time = datetime.utcnow()
    device_id = str(device_id)
    
    last_log = DeviceEventLog.query.filter_by(device_id=device_id, end_timestamp=None).first()
    
    if last_log:
        offline_duration = current_time - last_log.start_timestamp
        # Send second notification if offline for >= 60 minutes and less than 2 notifications have been sent
        if offline_duration >= timedelta(minutes=2) and last_log.offline_message_count < 2:
            return True
    return False

# Helper function to log the notification and increment the offline message count
def log_notification(device_id, current_time):
    """Log the time when the notification was sent and increment the offline message count."""
    device_id = str(device_id)
    
    existing_log = DeviceEventLog.query.filter_by(device_id=device_id, end_timestamp=None).first()

    if existing_log:
        existing_log.notification_timestamp = current_time
        existing_log.offline_message_count += 1  # Increment the offline message count
    else:
        # This should not happen as log_notification is called only when a log exists
        new_log = DeviceEventLog(
            device_id=device_id,
            start_timestamp=current_time,
            notification_timestamp=current_time,
            offline_message_count=1  # Start with 1 since it's the first notification
        )
        db.session.add(new_log)
    
    db.session.commit()
# API route for uploading device data


@api.route('/upload')
class UploadData(Resource):
    def post(self):
        data = request.json
        try:
            # Retrieve fields from the request
            hex_data = data.get('d')  # Expecting "d" for data
            wall_adapter_id = data.get('w')  # Expecting "g" for wall_adapter_id/gateway
            gas_device_id = data.get('g')  # Expecting "n" for gas_device_id/node

            # Convert hex string to bytes
            byte_data = bytes.fromhex(hex_data.strip())

            # Identify the message type (first byte)
            message_type = byte_data[0:1].hex()

            message_type_mappings = {
                "1d": "ALL DATA DUMPED",
                "2d": "No Data Node",
                "3d": "Connection type: NB-IoT",
                "4d": "Connection type: Wi-Fi",
                "5d": "Power source: Battery",
                "6d": "Power source: Electricity",
                "7d": "Gateway Battery < 20%",
                "8d": "Gateway Battery < 5%",
                "9d": "Gateway Battery < 2%",
                "1e": "Node Battery < 20%",
                "2e": "Node Battery < 5%",
                "3e": "Node Battery < 2%",
            }

            # Ensure the message type is valid
            if message_type not in message_type_mappings:
                return {"status": "error", "message": "Invalid or unsupported message type."}, 400

            # Set default values for data fields
            connection_type = wall_adapter_battery = power_source = weight = None
            gas_device_battery = wall_adapter_message_count = gas_device_message_count = None

            # Process data based on the message size
            if message_type in ["1d", "1e", "2e", "3e"]:  # 13 BYTES messages
                connection_type = byte_data[1:2].hex()
                power_source = byte_data[2:3].hex()  # 1 byte
                wall_adapter_battery = int(byte_data[3])  # 1 byte
                wall_adapter_message_count = struct.unpack('>I', b'\x00' + byte_data[4:7])[0]  # 3 bytes

                # Weight (2 bytes)
                weight_hex_part1 = byte_data[7:8].hex()  # 1 byte
                weight_hex_part2 = byte_data[8:9].hex()  # 1 byte
                weight = f"{int(weight_hex_part1, 16)}.{int(weight_hex_part2, 16):02d}"

                # Gas device fields (bytes data_index+8 to data_index+12)
                gas_device_battery = int(byte_data[9])  # 1 byte
                gas_device_message_count = struct.unpack('>I', b'\x00' + byte_data[10:13])[0]  # 3 bytes

            elif message_type in ["2d", "3d", "4d", "5d", "6d", "7d", "8d", "9d"]:  # 7 BYTES messages
                connection_type = byte_data[1:2].hex()
                power_source = byte_data[2:3].hex()  # 1 byte
                wall_adapter_battery = int(byte_data[3])  # 1 byte
                wall_adapter_message_count = struct.unpack('>I', b'\x00' + byte_data[4:7])[0]  # 3 bytes

            # Convert mappings to human-readable values
            connection_type_mapping = {"df": "NB-IoT", "de": "Wi-Fi"}
            power_source_mapping = {"c8": "Electricity", "c9": "Battery"}
            connection_type_human = connection_type_mapping.get(connection_type.lower(), "Unknown")
            power_source_human = power_source_mapping.get(power_source.lower(), "Unknown")

            # Fetch the wall adapter device based on wall_adapter_id from the request
            wall_adapter_device = Device.query.filter_by(wall_adapter_id=wall_adapter_id).first()
            if not wall_adapter_device:
                return {"status": "error", "message": "Invalid wall adapter device ID."}, 400

            # Fetch the paired device and associated user
            paired_device = PairedDevice.query.filter_by(matx_id=wall_adapter_device.matx_id).first()
            if not paired_device:
                return {"status": "error", "message": "Device is not paired with any user."}, 400

            user_email = paired_device.user.email

            # Save device data to the database
            device_data = DeviceData(
                wall_adapter_id=wall_adapter_id,
                gas_device_id=gas_device_id,
                user_id=paired_device.user.id,
                matx_id=wall_adapter_device.matx_id,
                data=byte_data  # Store the byte data
            )
            db.session.add(device_data)
            db.session.commit()

            return {
                "status": "success",
                "message": "Data uploaded successfully.",
                "data": {
                    "connection_type": connection_type_human,
                    "power_source": power_source_human,
                    "wall_adapter_battery": str(wall_adapter_battery) if wall_adapter_battery is not None else "N/A",
                    "wall_adapter_message_count": str(wall_adapter_message_count) if wall_adapter_message_count is not None else "N/A",
                    "weight": weight if weight else "N/A",
                    "gas_device_battery": str(gas_device_battery) if gas_device_battery is not None else "N/A",
                    "gas_device_message_count": str(gas_device_message_count) if gas_device_message_count is not None else "N/A"
                }
            }, 201

        except Exception as e:
            logging.error(f"Error processing the request: {str(e)}")
            return {"status": "error", "message": "An error occurred while processing the request."}, 500
        
@api.route('/user/<string:user_id>')
class GetUserData(Resource):
    def get(self, user_id):
        try:
            user = User.query.get(user_id)
            if not user:
                api.abort(404, f"User with ID {user_id} not found")

            paired_devices = PairedDevice.query.filter_by(user_id=user_id).all()
            result = []

            connection_type_map = {'de': 'Wi-Fi', 'df': 'NB-IoT'}
            power_source_map = {'c8': 'Electricity', 'c9': 'Battery'}

            for paired_device in paired_devices:
                device = Device.query.filter_by(matx_id=paired_device.matx_id).first()
                if device:
                    device_data_entries = DeviceData.query.filter_by(wall_adapter_id=device.wall_adapter_id).order_by(DeviceData.timestamp.desc()).all()

                    for data in device_data_entries:
                        gmt_plus_3_time = data.timestamp + timedelta(hours=3)
                        byte_data = data.data
                        message_type = byte_data[0:1].hex()

                        connection_type_hex = byte_data[1:2].hex()
                        power_source_hex = byte_data[2:3].hex()
                        wall_adapter_battery = int(byte_data[3:4].hex(), 16)

                        wall_adapter_message_count = struct.unpack('>I', b'\x00' + byte_data[4:7])[0]

                        gas_device_weight = None
                        gas_device_battery = None
                        gas_message_count = None

                        if len(byte_data) == 13:
                            weight_integer = int(byte_data[7:8].hex(), 16)
                            weight_decimal = int(byte_data[8:9].hex(), 16)
                            gas_device_weight = f"{weight_integer}.{weight_decimal:02d}"
                            gas_device_battery = int(byte_data[9:10].hex(), 16)
                            gas_message_count = struct.unpack('>I', b'\x00' + byte_data[10:13])[0]

                            # Call the method to update the gas usage based on the weight
                            data.update_gas_usage(gas_device_weight)

                        connection_type = connection_type_map.get(connection_type_hex.lower(), "Unknown")
                        power_source = power_source_map.get(power_source_hex.lower(), "Unknown")

                        result.append({
                            'device_id': device.wall_adapter_id,
                            'device_name': paired_device.name if paired_device else 'Unknown',
                            'date': gmt_plus_3_time.strftime('%d/%m/%Y'),
                            'time': gmt_plus_3_time.strftime('%H:%M'),
                            'connection_type': connection_type,
                            'power_source': power_source,
                            'wa_battery_status': str(wall_adapter_battery),
                            'wa_message_count': str(wall_adapter_message_count),
                            'gas_device_id': device.gas_device_id if hasattr(device, 'gas_device_id') else "Unknown",
                            'weight': gas_device_weight,
                            'gd_battery_status': str(gas_device_battery) if gas_device_battery is not None else "N/A",
                            'gd_message_count': str(gas_message_count) if gas_message_count is not None else "N/A",
                            'matx_id': device.matx_id
                        })

            return {"status": "success", "data": result}, 200

        except Exception as e:
            logging.error(f"Error retrieving user data for user_id {user_id}: {str(e)}")
            return {"status": "error", "message": "An error occurred while retrieving the user data"}, 500