# Use an official Python runtime as a base image
FROM python:3.10

# Set the working directory inside the container
WORKDIR /app

# Copy only the requirements file first (for better caching)
COPY requirements.txt .

# Install dependencies inside the container
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Expose the application port (e.g., 8000 for FastAPI)
EXPOSE 8000

# Default command to run the FastAPI app
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]