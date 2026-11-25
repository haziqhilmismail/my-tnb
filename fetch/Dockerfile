FROM python:3.12-slim
RUN pip install --no-cache-dir "python-mytnb[cli]==0.5.4"
COPY tnb_daily.py notes_api.py /app/
CMD ["python", "-u", "/app/tnb_daily.py"]
