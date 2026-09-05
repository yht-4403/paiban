import React from 'react';
import ReactDOM from 'react-dom/client';
import { ErrorBoundary } from './app/ErrorBoundary';
import { App } from './app/App';
import './styles.css';

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><ErrorBoundary><App /></ErrorBoundary></React.StrictMode>);
