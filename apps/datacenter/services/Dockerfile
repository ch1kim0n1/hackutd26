FROM python:3.12-slim
WORKDIR /app
COPY apps/datacenter/src /app/src
COPY apps/datacenter/services/vpi_service.py /app/vpi_service.py
ENV PYTHONPATH=/app/src
EXPOSE 8080
CMD ["python", "/app/vpi_service.py"]
