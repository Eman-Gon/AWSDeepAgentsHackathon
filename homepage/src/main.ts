import { App } from './App';
import { CommonsAuthClient } from './auth/auth-client';
import './styles.css';

document.addEventListener('DOMContentLoaded', () => {
  void bootstrap();
});

async function bootstrap(): Promise<void> {
  const root = document.getElementById('app');
  if (!root) throw new Error('Missing #app root');

  try {
    const auth = await CommonsAuthClient.create();
    const session = await auth.init();

    if (!session.isAuthenticated) {
      await auth.login();
      return;
    }

    new App(root, auth, session);
  } catch (error) {
    root.innerHTML = `
      <div class="auth-shell">
        <div class="auth-shell__card">
          <h1>Auth Setup Needed</h1>
          <p>${error instanceof Error ? error.message : 'Unable to initialize Auth0.'}</p>
          <p>Set the values in <code>homepage/.env.example</code> and restart the app.</p>
        </div>
      </div>
    `;
  }
}
