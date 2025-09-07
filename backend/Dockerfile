# Use the official Python image as the base image.
# We'll use a specific version for consistency.
FROM python:3.10-slim-buster

# Set the working directory to /app
WORKDIR /app

# Copy the entire backend directory into the container's working directory.
COPY . .

# Install Python dependencies from requirements.txt.
# It's assumed requirements.txt is in the same directory as the Dockerfile.
RUN pip install --no-cache-dir -r requirements.txt

# The command that runs when the container starts.
# It uses Gunicorn to run your Flask app, binding it to the PORT env var provided by Cloud Run.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
