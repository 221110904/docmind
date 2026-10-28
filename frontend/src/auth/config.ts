import type { Configuration } from "@azure/msal-browser";

export interface EntraSettings {
  tenantId: string;
  subdomain: string;
  clientId: string;
  apiScope: string;
}

/** Read the sign-in settings from the build environment; null when login is off. */
export function entraSettings(env: Record<string, string | undefined>): EntraSettings | null {
  if (env.VITE_AUTH !== "entra") return null;
  const missing = [
    "VITE_ENTRA_TENANT_ID",
    "VITE_ENTRA_SUBDOMAIN",
    "VITE_ENTRA_CLIENT_ID",
    "VITE_API_SCOPE",
  ].filter((name) => !env[name]);
  if (missing.length) {
    throw new Error(`VITE_AUTH=entra but ${missing.join(", ")} is not set in frontend/.env`);
  }
  return {
    tenantId: env.VITE_ENTRA_TENANT_ID!,
    subdomain: env.VITE_ENTRA_SUBDOMAIN!,
    clientId: env.VITE_ENTRA_CLIENT_ID!,
    apiScope: env.VITE_API_SCOPE!,
  };
}

export function msalConfig(settings: EntraSettings, origin: string): Configuration {
  const host = `${settings.subdomain}.ciamlogin.com`;
  // The tenant publishes its tokens under a second host named after the tenant ID. The
  // library only accepts that issuer when the host is listed here as well.
  const issuerHost = `${settings.tenantId}.ciamlogin.com`;
  return {
    auth: {
      clientId: settings.clientId,
      authority: `https://${host}/`,
      knownAuthorities: [host, issuerHost],
      redirectUri: origin,
      postLogoutRedirectUri: origin,
    },
    cache: { cacheLocation: "sessionStorage" },
  };
}
