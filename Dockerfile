FROM python:3.11-slim

WORKDIR /srv/app

# CPU-only torch keeps the image far smaller than the default CUDA build
COPY requirements.txt .
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

COPY . .

EXPOSE 8501

# Build indexes on first start if missing, then launch Streamlit
CMD ["/bin/sh", "-c", "if [ ! -f data/indexes/fixed/index.faiss ]; then python scripts/build_indexes.py; fi && streamlit run app/streamlit_app.py --server.port=8501 --server.address=0.0.0.0"]
