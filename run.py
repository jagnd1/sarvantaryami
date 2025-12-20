import uvicorn

if __name__ == "__main__":
    # Run the Sarvantaryamin Agent Web Service
    uvicorn.run("web.main:app", host="0.0.0.0", port=8010, reload=True)