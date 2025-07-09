# Use an official Python runtime as base image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy only necessary files
COPY requirements.txt .
COPY bot.py .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run the bot
CMD ["python", "bot.py"]

