FROM python:3.9-slim
WORKDIR /app
# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create asset directories
RUN mkdir -p /app/assets /app/fonts

# Copy assets into the container
COPY assets/next_airing_poster.jpg /app/assets/
COPY fonts/Juventus-Fans-Bold.ttf /app/fonts/

# Copy application code (all Python files directly)
COPY *.py ./

# Create volume mount points
VOLUME /app/config
VOLUME /app/data

# Set environment variable to indicate docker environment
ENV RUNNING_IN_DOCKER=true

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Set entrypoint
ENTRYPOINT ["docker-entrypoint.sh"]

# Default command shows help
CMD ["--help"]
