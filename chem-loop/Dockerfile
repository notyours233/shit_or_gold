# Pin the base digest used by the previous Harbor release.  This keeps local
# and server builds reproducible and lets BuildKit reuse the cached base when
# Docker Hub is temporarily unavailable.
FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install runtime deps (all Python; keep OS deps minimal)
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
  && python -m pip install --no-cache-dir -r /app/requirements.txt

# Copy the monorepo workspace
COPY . /app

# Keep data out of the image: all persistent state lives under /state (host-mounted).
# We wire the paths the code already expects to /state via symlinks.
RUN mkdir -p /state /state/jobs \
  # SQLite DB (UTU_DB_URL defaults to sqlite:///test.db relative to /app)
  && ln -sf /state/test.db /app/test.db \
  # MAD literature Chroma DB (material and reaction collections share one persist dir)
  && mkdir -p /app/MAD/data \
  && rm -rf /app/MAD/data/chroma_db \
  && ln -s /state/chroma_db /app/MAD/data/chroma_db \
  && rm -rf /app/MAD/data/chroma_db2 \
  && ln -s /state/chroma_db /app/MAD/data/chroma_db2 \
  # MAD experience packs (keep Python code in-place; only YAML packs are persisted)
  && mkdir -p /app/MAD/experience \
  && ln -sf /state/experience_mad.yaml /app/MAD/experience/experience.yaml \
  && rm -rf /app/MAD/experience/archive \
  && ln -s /state/experience_archive /app/MAD/experience/archive \
  # youtu-chem-loop stable experience pack
  && mkdir -p /app/youtu-chem-loop/configs/agents/practice \
  && ln -sf /state/experience_youtu.yaml /app/youtu-chem-loop/configs/agents/practice/experience.yaml

EXPOSE 8000

CMD ["python", "-m", "chemcouncil.server", "--host", "0.0.0.0", "--port", "8000"]
