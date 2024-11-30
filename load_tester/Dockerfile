FROM python:3.10-slim

WORKDIR /app

# Install necessary dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the load test script
COPY load_test.py .

# Default command to run the load test
CMD ["python", "load_test.py"]