import { render, screen } from '@testing-library/react';
import App from './App';

test('renders connection status text', () => {
  render(<App />);
  expect(screen.getByText(/connecting/i)).toBeInTheDocument();
});