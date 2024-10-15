# Use an official Python runtime as a parent image
FROM python:3.12-slim
# Set the working directory in the container
WORKDIR /app
# Copy the requirements file into the container
COPY common/requirements.txt .
# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
# Define environment variable
ENV FLASK_APP=app.py
# Run the application
CMD ["python", "main.py", "0.0.0.0:5000"]
