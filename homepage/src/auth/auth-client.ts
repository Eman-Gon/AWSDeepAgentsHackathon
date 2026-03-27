import { createAuth0Client, type Auth0Client, type IdToken } from '@auth0/auth0-spa-js';
import { getAuth0Config } from './auth-config';
import type { AuthSession, UserRole } from './types';

export class CommonsAuthClient {
  private client: Auth0Client;
  private config = getAuth0Config();

  private constructor(client: Auth0Client) {
    this.client = client;
  }

  static async create(): Promise<CommonsAuthClient> {
    const config = getAuth0Config();
    const client = await createAuth0Client({
      domain: config.domain,
      clientId: config.clientId,
      authorizationParams: {
        audience: config.audience,
        redirect_uri: config.redirectUri,
        scope: 'openid profile email',
      },
      cacheLocation: 'localstorage',
      useRefreshTokens: true,
    });

    return new CommonsAuthClient(client);
  }

  async init(): Promise<AuthSession> {
    if (window.location.search.includes('code=') && window.location.search.includes('state=')) {
      await this.client.handleRedirectCallback();
      window.history.replaceState({}, document.title, window.location.pathname);
    }

    const isAuthenticated = await this.client.isAuthenticated();
    if (!isAuthenticated) {
      return {
        isAuthenticated: false,
        userName: '',
        email: '',
        roles: [],
        isHuman: true,
        permissions: {
          canInvestigate: false,
          canPublish: false,
        },
      };
    }

    const user = await this.client.getUser();
    const claims = await this.client.getIdTokenClaims();
    const roles = this.getRolesFromClaims(claims);

    return {
      isAuthenticated: true,
      userName: user?.name || user?.nickname || user?.email || 'Authenticated User',
      email: user?.email || '',
      roles,
      isHuman: true,
      permissions: {
        canInvestigate: roles.includes('journalist') || roles.includes('editor'),
        canPublish: roles.includes('editor'),
      },
    };
  }

  async login(): Promise<void> {
    await this.client.loginWithRedirect({
      authorizationParams: {
        audience: this.config.audience,
        redirect_uri: this.config.redirectUri,
      },
    });
  }

  logout(): void {
    void this.client.logout({
      logoutParams: {
        returnTo: window.location.origin,
      },
    });
  }

  async getAccessToken(): Promise<string> {
    return this.client.getTokenSilently({
      authorizationParams: {
        audience: this.config.audience,
      },
    });
  }

  private getRolesFromClaims(claims: IdToken | undefined): UserRole[] {
    if (!claims) return [];

    const namespacedRoles = claims[`${this.config.claimsNamespace}/roles`];
    const roles = Array.isArray(namespacedRoles) ? namespacedRoles : [];
    return roles.filter((role): role is UserRole => role === 'journalist' || role === 'editor');
  }
}
