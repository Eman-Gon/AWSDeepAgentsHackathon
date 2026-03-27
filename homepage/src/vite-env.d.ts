/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AUTH0_DOMAIN: string;
  readonly VITE_AUTH0_CLIENT_ID: string;
  readonly VITE_AUTH0_AUDIENCE?: string;
  readonly VITE_AUTH0_REDIRECT_URI: string;
  readonly VITE_AUTH0_CLAIMS_NAMESPACE?: string;
  readonly VITE_AUTH_DEV_BYPASS?: string;
}

declare module '*.css' {
  const content: string;
  export default content;
}
