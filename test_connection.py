from dotenv import load_dotenv
from elasticsearch import Elasticsearch
import os

load_dotenv()

es = Elasticsearch(
    os.environ["ELASTIC_CLOUD_URL"],
    api_key=os.environ["ELASTIC_API_KEY"]
)

info = es.info()
print("Connected to Elastic!")
print(f"Cluster: {info['cluster_name']}")
print(f"Version: {info['version']['number']}")
