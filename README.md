# McDonald's Ordering Simulator

A text-based AI ordering assistant for McDonald's, featuring a FastAPI server, a command-line client, and LLM integration via Cerebras.

## Prerequisites

- **Python**: 3.12 or 3.13
- **Poetry**: Package manager
- **Docker**: (Optional) For containerized execution
- **Cerebras API Key**: Required for LLM functionality

## Configuration

Create a `.env` file in the root directory to store your API key. After that, add the following line to `.env`:

```env
CEREBRAS_API_KEY=your_api_key_here
```

## Installation

1.  **Install Dependencies**

    ```bash
    poetry install
    ```

2.  **Run the Server**
    Start the backend server (default port 8000):

    ```bash
    poetry run mcd-cli serve
    ```

3.  **Run the Client**
    In a separate terminal window, start the interactive chat client:

    ```bash
    poetry run mcd-cli chat
    ```

## Running with Docker

1.  **Build the Image**

    ```bash
    docker build -t mcd-cli .
    ```

2.  **Run the Container**
    Map port 8000 and pass your environment variables (or mount the `.env` file):

    ```bash
    docker run -p 8000:8000 --env-file .env mcd-cli
    ```

3.  **Connect with Client**
    Once the Docker container is running the server, you can connect using the local client:

    ```bash
    poetry run mcd-cli chat
    ```