export interface Auth0AppConfig {
  domain: string;
  clientId: string;
  redirectUri: string;
  audience?: string;
  claimsNamespace: string;
  devBypass: boolean;
}

function readEnv(key: string): string | undefined {
  const value = import.meta.env[key];
  return value && typeof value === 'string' ? value : undefined;
}

function requireEnv(key: string): string {
  const value = readEnv(key);
  if (!value) {
    throw new Error(`Missing required Auth0 config: ${key}`);
  }
  return value;
}

function normalizeAudience(value: string | undefined): string | undefined {
  if (!value) return undefined;
  if (value === 'https://commons-api') return undefined;
  return value;
}

export function getAuth0Config(): Auth0AppConfig {
  return {
    domain: requireEnv('VITE_AUTH0_DOMAIN'),
    clientId: requireEnv('VITE_AUTH0_CLIENT_ID'),
    redirectUri: requireEnv('VITE_AUTH0_REDIRECT_URI'),
    audience: normalizeAudience(readEnv('VITE_AUTH0_AUDIENCE')),
    claimsNamespace: readEnv('VITE_AUTH0_CLAIMS_NAMESPACE') || 'https://commons.app',
    devBypass: readEnv('VITE_AUTH_DEV_BYPASS') === 'true',
  };
}

export function getAuth0ConfigError(): string | null {
  try {
    getAuth0Config();
    return null;
  } catch (error) {
    return error instanceof Error ? error.message : 'Missing Auth0 configuration';
  }
}
