This project is a FastAPI application containerized with Docker and managed using Docker Compose. It enables seamless development with hot-reloading and efficient dependency management.

Prerequisites
Ensure you have Docker and Docker Compose installed on your system. These tools allow you to run the application in a containerized environment without needing to install dependencies manually.

Getting Started
Clone the repository and navigate to the project directory:
git clone <your-repo-url>
cd <your-repo-name>
If your application requires environment variables, create a .env file in the project root with necessary configurations.

Building and Running the Project
To build and run the container, use:
docker-compose up --build

After the initial build, you can start the project without rebuilding by running:
docker-compose up

The API will be accessible at http://localhost:8000, with interactive API documentation at:
Swagger UI: http://localhost:8000/docs
ReDoc: http://localhost:8000/redoc
Stopping the Application

To stop the running container, use:
docker-compose down
