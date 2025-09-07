# Use the official Python image as the base image.
# We'll use a specific version for consistency.
FROM python:3.10-slim-buster

# Set the working directory to /app
WORKDIR /app

# Copy only the requirements file into the container first.
# This is crucial. It tells Docker to copy requirements.txt from the backend/ directory
# of the build context (which is the root of your repo).
COPY backend/requirements.txt .

# Install Python dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's source code into the container.
# This copies everything else from the backend/ directory.
COPY backend/ .

# The command that runs when the container starts.
# It uses Gunicorn to run your Flask app, binding it to the PORT env var provided by Cloud Run.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]