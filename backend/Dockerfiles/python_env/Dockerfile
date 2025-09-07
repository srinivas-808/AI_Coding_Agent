# Use the official Python image as the base image.
FROM python:3.9-slim-buster

# Set the working directory to /app
WORKDIR /app

# Copy the Flask application files from your backend directory into the container
COPY . .

# Install Python dependencies from requirements.txt.
RUN pip install --no-cache-dir -r requirements.txt

# The command that runs when the container starts.
# It uses Gunicorn to run your Flask app, binding it to the PORT env var provided by Cloud Run.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]