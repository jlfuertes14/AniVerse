FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Switch to existing non-root user (pwuser has UID 1000 in Playwright images)
USER pwuser
ENV HOME=/home/pwuser \
	PATH=/home/pwuser/.local/bin:$PATH

WORKDIR $HOME/app

COPY --chown=pwuser . $HOME/app

# Install python dependencies
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Create cache directory for scraper runner if needed
RUN mkdir -p $HOME/app/.cache

EXPOSE 7860

# Command to run FastAPI server (uvicorn)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
