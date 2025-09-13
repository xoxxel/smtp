FROM python:3.11-slim


# Install deps
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Copy app
COPY app.py .


# Expose ports (SMTP 2525 + HTTP healthcheck 8080)
EXPOSE 2525 8080


CMD ["python", "app.py"]