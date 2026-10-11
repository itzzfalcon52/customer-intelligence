import { useState } from 'react';
import { z } from 'zod';

const healthSchema = z.object({
  status: z.literal('ok'),
  service: z.string(),
});

type HealthResponse = z.infer<typeof healthSchema>;

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function checkBackend() {
    setLoading(true);
    setError(null);
    setHealth(null);

    try {
      const response = await fetch('/api/v1/health', {
        cache: 'no-store',
      });

      if (!response.ok) {
        throw new Error(`Backend returned HTTP ${response.status}`);
      }

      const data = healthSchema.parse(await response.json());
      setHealth(data);
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : 'Could not connect to the backend.',
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <h1>Customer Intelligence</h1>
      <p>Check the connection between React and FastAPI.</p>

      <button onClick={checkBackend} disabled={loading}>
        {loading ? 'Checking...' : 'Check backend'}
      </button>

      {health && (
        <p role="status">
          Connected to {health.service}. Status: {health.status}
        </p>
      )}

      {error && <p role="alert">{error}</p>}
    </main>
  );
}