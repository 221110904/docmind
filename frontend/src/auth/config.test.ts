import { describe, expect, it } from "vitest";
import { entraSettings, msalConfig } from "./config";

const env = {
  VITE_AUTH: "entra",
  VITE_ENTRA_TENANT_ID: "tenant-1",
  VITE_ENTRA_SUBDOMAIN: "docmindauth",
  VITE_ENTRA_CLIENT_ID: "client-1",
  VITE_API_SCOPE: "api://api-1/access_as_user",
};

describe("entraSettings", () => {
  it("is off unless VITE_AUTH is entra", () => {
    expect(entraSettings({})).toBeNull();
    expect(entraSettings({ ...env, VITE_AUTH: "off" })).toBeNull();
  });

  it("reads the four settings", () => {
    expect(entraSettings(env)).toEqual({
      tenantId: "tenant-1",
      subdomain: "docmindauth",
      clientId: "client-1",
      apiScope: "api://api-1/access_as_user",
    });
  });

  it("says exactly which setting is missing", () => {
    expect(() => entraSettings({ ...env, VITE_API_SCOPE: "" })).toThrow(/VITE_API_SCOPE/);
    expect(() => entraSettings({ VITE_AUTH: "entra" })).toThrow(
      /VITE_ENTRA_TENANT_ID, VITE_ENTRA_SUBDOMAIN, VITE_ENTRA_CLIENT_ID, VITE_API_SCOPE/,
    );
  });
});

describe("msalConfig", () => {
  it("points at the External ID tenant and returns to this site", () => {
    const config = msalConfig(entraSettings(env)!, "http://localhost:5173");
    expect(config.auth.authority).toBe("https://docmindauth.ciamlogin.com/");
    // Both hosts: the tenant's name, and the tenant-ID host that appears in its issuer.
    expect(config.auth.knownAuthorities).toEqual([
      "docmindauth.ciamlogin.com",
      "tenant-1.ciamlogin.com",
    ]);
    expect(config.auth.clientId).toBe("client-1");
    expect(config.auth.redirectUri).toBe("http://localhost:5173");
    expect(config.auth.postLogoutRedirectUri).toBe("http://localhost:5173");
  });
});
