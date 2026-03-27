import { h, render } from 'preact';
import { Auth0Provider } from '@auth0/auth0-react';
import { App } from './App';
import { getAuth0Config, getAuth0ConfigError } from './auth/auth-config';
import './styles.css';

document.addEventListener('DOMContentLoaded', () => {
  bootstrap();
});

function bootstrap(): void {
  const root = document.getElementById('app');
  if (!root) throw new Error('Missing #app root');

  const devBypass = import.meta.env.VITE_AUTH_DEV_BYPASS === 'true';
  if (devBypass) {
    render(h(App, { devBypass: true }), root);
    return;
  }

  const error = getAuth0ConfigError();
  if (error) {
    root.innerHTML = `
      <div class="auth-shell">
        <div class="auth-shell__card">
          <h1>Auth Setup Needed</h1>
          <p>${error}</p>
          <p>Set the Auth0 values in your Vite env file and restart the app.</p>
        </div>
      </div>
    `;
    return;
  }

  const config = getAuth0Config();

  render(
    h(
      Auth0Provider,
      {
        domain: config.domain,
        clientId: config.clientId,
        authorizationParams: {
          redirect_uri: config.redirectUri,
          ...(config.audience ? { audience: config.audience } : {}),
        },
      },
      h(App, {}),
    ),
    root,
  );
}
