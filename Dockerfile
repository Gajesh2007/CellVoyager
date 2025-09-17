# syntax=docker/dockerfile:1.7
FROM mambaorg/micromamba:1.5.8

# Auto-activate base env in subsequent RUN/CMD/ENTRYPOINT
ARG MAMBA_DOCKERFILE_ACTIVATE=1

WORKDIR /app

# Install conda/pip dependencies from environment file
COPY --chown=$MAMBA_USER:$MAMBA_USER CellVoyager_env.yaml /tmp/env.yaml
RUN micromamba install -y -n base -f /tmp/env.yaml \
    && micromamba clean -a -y

# Environment for reliable, headless execution
ENV MPLBACKEND=Agg \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    PATH=/opt/conda/bin:$PATH

# Copy source
COPY --chown=$MAMBA_USER:$MAMBA_USER . /app

# Example dataset is copied from the repository (ensure .dockerignore does not exclude it)

# Ensure downstream layered builds (e.g., EigenCloud) run as root so they can modify /usr/local/bin
USER root

# Default command; conda's Python is on PATH so this runs the app directly
CMD ["python", "run.py"]


