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
    PYTHONIOENCODING=UTF-8

# Copy source
COPY --chown=$MAMBA_USER:$MAMBA_USER . /app

# Download the example dataset so defaults work out-of-the-box (use wget inside conda env)
RUN micromamba install -y -n base -c conda-forge wget \
    && micromamba clean -a -y
RUN mkdir -p example \
    && micromamba run -n base wget -O example/covid19.h5ad "https://hosted-matrices-prod.s3-us-west-2.amazonaws.com/Single_cell_atlas_of_peripheral_immune_response_to_SARS_CoV_2_infection-25/Single_cell_atlas_of_peripheral_immune_response_to_SARS_CoV_2_infection.h5ad"

# Provide a simple entrypoint; ensure conda env is active at runtime
ENTRYPOINT ["micromamba", "run", "-n", "base", "--", "python", "run.py"]
CMD []


