// frontend/functions/api/[[path]].ts
// Forwards every /api/* request to the backend, so the browser stays on one origin.
export const onRequest = async ({
  request,
  env,
}: {
  request: Request;
  env: { BACKEND_URL: string };
}) => {
  const url = new URL(request.url);
  const target = new URL(url.pathname + url.search, env.BACKEND_URL);
  return fetch(new Request(target, request));
};
