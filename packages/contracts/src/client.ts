import createClient from "openapi-fetch";
import type { paths } from "./schema";

export type { paths, components } from "./schema";

/** Typed fetch client for services/api. Every path/method/body/response
 * shape is inferred from the generated `paths` type -- a route that
 * doesn't exist, or a body that doesn't match, is a compile error here,
 * not a runtime surprise. Regenerate via `pnpm --filter contracts generate`
 * whenever services/api's routes or Pydantic schemas change. */
export function createApiClient(baseUrl: string, getAuthToken: () => Promise<string | null>) {
  const client = createClient<paths>({ baseUrl });

  client.use({
    async onRequest({ request }) {
      const token = await getAuthToken();
      if (token) {
        request.headers.set("Authorization", `Bearer ${token}`);
      }
      return request;
    },
  });

  return client;
}

export type ApiClient = ReturnType<typeof createApiClient>;
