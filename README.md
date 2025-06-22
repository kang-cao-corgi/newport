## Rental price scraper

- install [uv](https://docs.astral.sh/uv/getting-started/installation/)
- install python
    ```
    uv python install 3.11.2
    ```
- run script
    ```
    uv run python main.py
    ```

    After script finishes, there will be a new .csv file created

- test run in docker
  ```bash
  docker build . -t newport

  docker run --mount type=bind,source=$(pwd)/output,target=/app/output newport:latest
  ```