# Use official Python slim image
FROM python:3.11-slim

# Install ffmpeg and other dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install gunicorn explicitly
RUN pip install --no-cache-dir gunicorn

# Copy all project files
COPY . .

# Expose port (Railway default)
EXPOSE 8080

# Run the app with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
