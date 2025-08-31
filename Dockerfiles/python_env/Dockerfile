# ai_coding_agent/Dockerfiles/python_env/Dockerfile

# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install any necessary dependencies if your generated code might need them
# For now, we'll keep it bare minimum.
# RUN pip install numpy pandas  # Uncomment and add if you foresee needing these

# Command to run a Python script named 'runner.py'
# This will be overridden when we execute our specific generated code
CMD ["python", "runner.py"]