class Config:
    SQLALCHEMY_DATABASE_URI = 'postgresql://bett:Bett123456@matxiotdbdev.c36k8kooes7j.me-central-1.rds.amazonaws.com/matxiotdbdev'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = 'your_secret_key'  
    JWT_ACCESS_TOKEN_EXPIRES = False  
    


# class Config:
#     SQLALCHEMY_DATABASE_URI = 'postgresql://bett:Bett1234@localhost/matxiotdev'
#     SQLALCHEMY_TRACK_MODIFICATIONS = False
#     SECRET_KEY = 'your_secret_key'  
#     JWT_ACCESS_TOKEN_EXPIRES = False  
    