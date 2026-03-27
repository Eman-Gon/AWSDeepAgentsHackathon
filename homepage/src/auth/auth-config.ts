export interface Auth0AppConfig {
  domain: string;
  clientId: string;
  audience: string;
  redirectUri: string;
  claimsNamespace: string;
}

function requireEnv(key: string): string {
  const value = import.meta.env[key];
  if (!value || typeof value !== 'string') {
    throw new Error(`Missing required Auth0 config: ${key}`);
  }
  return value;
}

export function getAuth0Config(): Auth0AppConfig {
  return {
    domain: requireEnv('VITE_AUTH0_DOMAIN'),
    clientId: requireEnv('VITE_AUTH0_CLIENT_ID'),
    audience: requireEnv('VITE_AUTH0_AUDIENCE'),
    redirectUri: import.meta.env.VITE_AUTH0_REDIRECT_URI || window.location.origin,
    claimsNamespace: import.meta.env.VITE_AUTH0_CLAIMS_NAMESPACE || 'https://commons.app',
  };
}
