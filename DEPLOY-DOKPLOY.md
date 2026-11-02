# Deploy the full-stack assessment with Dokploy

This app is a single Docker service: Django serves the built React app and `/api` from the same origin. Gunicorn listens on **container port 8000** by default. No database, separate frontend service or public browser API key is required.

The current deployment is [spotter-weather.dev-link.cloud](https://spotter-weather.dev-link.cloud/), created and browser verified on 2 November 2026. The steps below describe its reproducible setup; do not create a duplicate service merely to redeploy the existing app.

1. In Dokploy, create an **Application** in the intended project. Connect the standalone full-stack GitHub repository through your GitHub integration. The current repository is public; private forks require appropriate integration access. Select its actual default branch.
2. Select **Dockerfile** as the build type, repository root as the build path, and `Dockerfile` as the Dockerfile path. If deploying the combined workspace instead, the build path is `/fullstack-weather-assessment` with that directory's `Dockerfile`.
3. In the application's environment settings, set:

   ```dotenv
   DEBUG=false
   SECRET_KEY=<generate-a-new-private-random-value-in-your-secret-store>
   ALLOWED_HOSTS=<the-actual-public-hostname-without-scheme-or-path>
   PORT=8000
   PROVIDER_TIMEOUT_SECONDS=15
   ```

   Use a real secret, never the literal example. Keep environment configuration in Dokploy. Provider endpoints have working defaults in `backend/config/settings.py`. Add `OPEN_METEO_API_KEY` and its matching provider URL only if using a plan that requires them.

4. In **Domains**, add the chosen or generated hostname. Set **Path** `/`, **Container Port** `8000`, and HTTPS/certificate settings appropriate to that hostname. Leave internal path rewriting unnecessary for this root-served application. Match `ALLOWED_HOSTS` to the hostname before deployment. Dokploy's domain container-port setting routes internal proxy traffic; no direct public host-port mapping is needed.
5. Deploy and inspect build/startup logs. Configure a health check, if the selected Dokploy service settings expose it, as `GET /api/health/` on port 8000; a successful response is HTTP 200 with `status: "ok"`.
6. Open the public root URL in a clean browser, run a live trip and check all of: three distinct road options, route selection/checkpoints, ETA weather, recommendation, slider endpoints 0 and 48, and visible forecast errors. Check the browser console and application logs. Test that `/api/health/` and built `/assets/` files are reachable on the same public origin.

The image builds React using `npm ci` and the committed lockfile, installs pinned Python dependencies, copies `frontend/dist` into the final image and runs as a non-root user. Its file cache is local runtime data; it can be recreated after a redeploy. Container health proves the service is running, while a live trip additionally verifies outbound access to routing/geocoding/weather providers. A valid offline demonstration does not prove live provider connectivity.

If a deployment fails, inspect the actual build/runtime logs before retrying. Typical configuration checks are the Docker build path, installed dependencies, `SECRET_KEY`, `DEBUG`, exact `ALLOWED_HOSTS`, container port and provider availability. The GitHub repository, Dokploy application ID, public URL and successful verification should be recorded in the project README once real values exist.

References: [Dokploy applications](https://docs.dokploy.com/docs/core/applications), [Dockerfile application example](https://docs.dokploy.com/docs/core/deno), [Dokploy domains and container ports](https://docs.dokploy.com/docs/core/domains).
