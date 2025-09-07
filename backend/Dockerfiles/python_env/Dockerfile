# Use the official Python image as the base image.
# It's better to pin a specific version for consistency.
FROM python:3.9-slim-buster

# Set the working directory to /app
WORKDIR /app

# Copy the entire backend directory into the container's working directory
COPY ../../backend/ ./

# Install Python dependencies from requirements.txt.
# We'll create this file in the next step.
# This single command ensures the build cache is effective.
RUN pip install --no-cache-dir Flask requests python-dotenv

# Tell the container to expose port 8080
EXPOSE 8080

# This command runs when the container starts.
# It uses Gunicorn, a production-ready WSGI server, to run your Flask application.
# It binds to the host '0.0.0.0' and the port provided by Cloud Run's PORT env var.
# The 'app:app' syntax refers to the 'app' object inside the 'app.py' module.
CMD exec gunicorn --bind 0.0.0.0:8080 --workers 1 --threads 8 --timeout 0 app:app
