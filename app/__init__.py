from flask import Flask
from flask_restx import Api
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from app.user_management.models import User
from config import Config
from common.db import db

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize Flask extensions
    db.init_app(app)
    migrate = Migrate(app, db)  # Initialize Migrate
    jwt = JWTManager(app)  # Initialize JWTManager with the Flask app instance

    api = Api(app, version='1.0', title='matX IoT API',
              description='A microservices architecture for gas monitoring',doc=False)

    # Import and register namespaces for each microservice
    from app.user_management.routes import api as user_management_api
    from app.device_registry.routes import api as device_registry_api
    from app.paired_devices_registry.routes import api as paired_devices_registry_api
    from app.device_data_registry.routes import api as device_data_registry_api
    from app.cylinder_registry.routes import api as cylinder_registry_api

    # Add namespaces to the Api instance
    api.add_namespace(user_management_api, path='/users')
    api.add_namespace(device_registry_api, path='/devices')
    api.add_namespace(paired_devices_registry_api, path='/assign-devices')
    api.add_namespace(device_data_registry_api, path='/data')
    api.add_namespace(cylinder_registry_api, path='/gas')


    # Initialize database tables
    with app.app_context():
        # db.drop_all()
        db.create_all()

    return app
