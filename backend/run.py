from spotify_frame_backend.app import create_app


app = create_app()


if __name__ == "__main__":
    app.run(host=app.config["SETTINGS"].host, port=app.config["SETTINGS"].port, threaded=True)
