FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Switch to non-root user (Hugging Face Spaces requirement)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
	PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

COPY --chown=user . $HOME/app

# Install python dependencies
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Create cache directory for scraper runner if needed
RUN mkdir -p $HOME/app/.cache

EXPOSE 7860

# Command to run FastAPI server (uvicorn)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
