import { App } from './App';
import './styles.css';

document.addEventListener('DOMContentLoaded', () => {
  const root = document.getElementById('app');
  if (!root) throw new Error('Missing #app root');
  new App(root);
});
