from fastapi import FastAPI
app = FastAPI()
application = app

def start_response(status, headers):
    print(status, headers)

try:
    application({}, start_response)
except Exception as exc:
    print(type(exc).__name__, exc)

