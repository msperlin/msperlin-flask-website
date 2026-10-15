# Use the official lightweight Python image.
# https://hub.docker.com/_/python
FROM python:3.13-slim

# Install uv (fast Python package manager) from the official image.
# https://docs.astral.sh/uv/guides/integration/docker/
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8

# Copy local code to the container image.
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./

# Install production dependencies from the lockfile (reproducible builds).
RUN uv sync --frozen --no-dev

# Put the project virtual environment on PATH so gunicorn is available.
ENV PATH="$APP_HOME/.venv/bin:$PATH"

# Run the web service on container startup. Here we use the gunicorn
# webserver, with one worker process and 8 threads.
# For environments with multiple CPU cores, increase the number of workers
# to be equal to the cores available.
# Timeout is set to 0 to disable the timeouts of the workers to allow Cloud Run to handle instance scaling.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app
