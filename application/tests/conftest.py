"""Unit tests must never load the operator's private deployment settings."""
import os
os.environ['SHIXU_SKIP_DOTENV']='true'
os.environ['SHIXU_BACKEND']='sqlite'
os.environ['SHIXU_PUBLIC_URL']=''
os.environ['SHIXU_HTTPS_PROXY_SECRET']=''
os.environ['SHIXU_ALLOW_HTTP_AUTH']='false'
