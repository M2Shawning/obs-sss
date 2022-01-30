# OBS Stupid Simple Switcher | obs-sss

GraphQL API and Web App for managing multiple OBS clients through WebSockets.

## Disclaimer

This is a random project with no warranty or support given. I am writing this for my own purposes. This is only public so others may grab code here and there.

## Status

No production build has been developed yet. Current state this repository does nothing.

## Testing

- Create python.env with needed environment variables
- Run `docker-compose up -d --build` to create the dev container
- Run `docker exec -it obs-sss uvicorn --host 0.0.0.0 main:app --reload` to start the webserver
